#!/usr/bin/env python3
"""uConsole camera hub: one video source and one detector shared by every screen."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import mimetypes
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import uuid
from urllib.parse import parse_qs, urlsplit
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler

from stream import jpeg_frames, MAX_FRAME
from ring_feed import RingFeed, RING_CAMERAS, RING_LIMITS

ROOT = Path(__file__).resolve().parent
SOURCES = ('home', 'field', 'phone', 'drone', *RING_CAMERAS)


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Hub:
    def __init__(self, targets, settings, model, threads=2, detection_hz=2):
        self.targets, self.settings, self.model = targets, settings, model
        self.threads, self.detection_hz = threads, detection_hz
        self.condition = threading.Condition()
        self.source, self.enabled = 'home', True
        try:
            saved = json.loads(settings.read_text())
            if saved.get('source') in SOURCES:
                self.source = saved['source']
            self.enabled = bool(saved.get('detection', True))
        except (OSError, ValueError):
            pass
        self.epoch, self.revision = uuid.uuid4().hex, 0
        self.frame, self.frame_id, self.received = None, 0, 0.
        self.last_view = 0.
        self.error = 'Connecting to camera…'
        self.ring_active, self.ring_deadline, self.ring_generation = False, 0., 0
        if self.source in RING_CAMERAS:
            self.error = 'Press Start live view to open this Ring camera.'
        self.phone_owner, self.phone_received = None, 0.
        self.people, self.result_frame, self.result_received = [], 0, 0.
        self.vehicles = []
        self.inference_ms, self.inference_count = 0., 0
        self.detector_status = 'Loading detection…'
        self.opener = build_opener(ProxyHandler({}), NoRedirects())
        threading.Thread(target=self.camera_loop, name='camera-feed', daemon=True).start()
        threading.Thread(target=self.detect_loop, name='shared-detector', daemon=True).start()

    def snapshot(self):
        with self.condition:
            now = time.monotonic()
            if self.ring_active and now >= self.ring_deadline:
                self.stop_ring_locked('Ring session finished. Press Start live view for another session.')
            self.last_view = now
            self.condition.notify_all()
            fresh = self.frame is not None and now - self.received < 2
            age = (now - self.result_received) * 1000
            people = self.people if fresh and self.enabled and age < 1600 else []
            vehicles = self.vehicles if fresh and self.enabled and age < 1600 else []
            return {'app': 'uconsole-camera-hub', 'version': 5, 'epoch': self.epoch,
                    'source': self.source, 'revision': self.revision, 'detection': self.enabled,
                    'live': fresh, 'error': self.error if not fresh else '',
                    'frame_id': self.frame_id, 'people': people, 'vehicles': vehicles,
                    'capabilities': {'people': True, 'vehicles': True, 'police': False},
                    'ring': {'selected': self.source in RING_CAMERAS, 'active': self.ring_active,
                             'remaining_seconds': max(0, int(self.ring_deadline-now)) if self.ring_active else 0,
                             'session_seconds': RING_LIMITS.get(self.source, 0)},
                    'result_frame': self.result_frame, 'result_age_ms': round(age) if self.result_received else None,
                    'inference_ms': round(self.inference_ms, 1), 'inference_count': self.inference_count,
                    'detector_status': self.detector_status, 'detection_limit_hz': self.detection_hz}

    def control(self, data):
        if set(data) - {'source', 'detection', 'ring_action'}:
            raise ValueError('Unknown camera setting')
        if 'source' in data and data['source'] not in SOURCES:
            raise ValueError('Unknown camera source')
        if 'detection' in data and type(data['detection']) is not bool:
            raise ValueError('Detection must be on or off')
        if 'ring_action' in data and data['ring_action'] not in ('start', 'stop'):
            raise ValueError('Unknown Ring action')
        with self.condition:
            source = data.get('source', self.source)
            enabled = data.get('detection', self.enabled)
            action = data.get('ring_action')
            if action is not None and source not in RING_CAMERAS:
                raise ValueError('Select a Ring camera first')
            if source != self.source or enabled != self.enabled or action is not None:
                source_changed = source != self.source
                # Persist before applying so a failed write cannot silently lose the selection.
                self.settings.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.settings.with_suffix('.tmp')
                temporary.write_text(json.dumps({'source': source, 'detection': enabled}))
                temporary.replace(self.settings)
                self.source, self.enabled = source, enabled
                self.revision += 1
                self.people, self.result_received = [], 0.
                self.vehicles = []
                if source_changed or action is not None:
                    self.frame, self.received = None, 0.
                    self.ring_generation += 1
                    self.ring_active = source in RING_CAMERAS and action != 'stop'
                    self.ring_deadline = time.monotonic()+RING_LIMITS[source] if self.ring_active else 0.
                    self.error = ('Keep PotensicPro visible on the paired Android. Connecting to its screen…' if source == 'drone'
                                  else 'On the phone, tap Start camera and keep that page open.' if source == 'phone'
                                  else ('Connecting to Ring…' if self.ring_active else 'Ring live view stopped. Press Start live view to reconnect.') if source in RING_CAMERAS
                                  else 'Connecting to camera…')
                self.condition.notify_all()

    def stop_ring_locked(self, message):
        self.ring_active, self.ring_deadline = False, 0.
        self.ring_generation += 1
        self.frame, self.received, self.result_received = None, 0., 0.
        self.people, self.vehicles = [], []
        self.error = message
        self.condition.notify_all()

    def publish_locked(self, frame):
        self.frame, self.received = frame, time.monotonic()
        self.frame_id += 1
        self.error = 'Waiting for a fresh camera frame…'
        self.condition.notify_all()

    def phone_publish(self, owner, frame):
        with self.condition:
            now = time.monotonic()
            if self.phone_owner not in (None, owner) and now - self.phone_received < 5:
                raise ConnectionError('Another phone is sending. Stop its camera first.')
            self.phone_owner, self.phone_received = owner, now
            if self.source == 'phone':
                self.publish_locked(frame)

    def phone_stop(self, owner):
        with self.condition:
            if self.phone_owner == owner:
                self.phone_owner = None
                if self.source == 'phone':
                    self.frame, self.people = None, []
                    self.vehicles = []
                    self.error = 'Phone camera stopped. Tap Start camera on the phone.'
                    self.condition.notify_all()

    def get_frame(self, after):
        deadline = time.monotonic() + 2.5
        with self.condition:
            self.last_view = time.monotonic()
            self.condition.notify_all()
            while time.monotonic() < deadline:
                if self.frame is not None and self.frame_id != after and time.monotonic()-self.received < 2:
                    return self.frame, self.frame_id, self.source, self.revision
                self.condition.wait(max(.01, deadline-time.monotonic()))
            raise ConnectionError(self.error)

    def camera_loop(self):
        while True:
            with self.condition:
                while (self.source == 'phone' or time.monotonic()-self.last_view > 6
                       or (self.source in RING_CAMERAS and not self.ring_active)):
                    if self.ring_active and time.monotonic()-self.last_view > 6:
                        self.stop_ring_locked('Ring live view stopped while unused. Press Start live view to reconnect.')
                    self.condition.wait(1)
                source = self.source
                generation = self.ring_generation
            try:
                if source in RING_CAMERAS:
                    with RingFeed(source) as feed:
                        while True:
                            with self.condition:
                                if self.source != source or self.ring_generation != generation or not self.ring_active:
                                    break
                                now = time.monotonic()
                                if now >= self.ring_deadline or now-self.last_view > 6:
                                    self.stop_ring_locked('Ring live view ended. Press Start live view for another session.')
                                    break
                            frame = feed.next_frame()
                            if frame is not None:
                                with self.condition:
                                    if self.source != source or self.ring_generation != generation or not self.ring_active:
                                        break
                                    self.publish_locked(frame)
                    continue
                if source == 'drone':
                    from drone import DroneFeed
                    with DroneFeed() as feed:
                        while True:
                            with self.condition:
                                if self.source != source or time.monotonic()-self.last_view > 6: break
                            frame = feed.next_frame()
                            if frame is not None:
                                with self.condition:
                                    if self.source != source: break
                                    self.publish_locked(frame)
                    continue
                response = None
                for target in self.targets[source]:
                    try:
                        response = self.opener.open(target, timeout=4)
                        break
                    except (OSError, ValueError):
                        continue
                if response is None:
                    raise ConnectionError('Camera unreachable. Check its power and your Wi-Fi connection.')
                last_publish = 0.
                with response:
                    for frame in jpeg_frames(response):
                        with self.condition:
                            now = time.monotonic()
                            if source != self.source or now-self.last_view > 6:
                                break
                            if now-last_publish >= .095:
                                self.publish_locked(frame)
                                last_publish = now
            except (OSError, ValueError) as exc:
                with self.condition:
                    if self.source == source:
                        if source in RING_CAMERAS:
                            if generation == self.ring_generation:
                                self.stop_ring_locked(str(exc))
                        else:
                            self.frame, self.people = None, []
                            self.vehicles = []
                            self.error = str(exc)
                        self.condition.notify_all()
                time.sleep(2 if source == 'drone' else .5)

    def detect_loop(self):
        try:
            from detector import PersonDetector
            detector = PersonDetector(self.model, self.threads)
        except Exception as exc:
            with self.condition:
                self.detector_status = 'Detection unavailable: ' + str(exc)
            return
        last_id, next_run = 0, 0.
        with self.condition:
            self.detector_status = 'Detection ready'
        while True:
            with self.condition:
                now = time.monotonic()
                if (not self.enabled or self.frame is None or self.frame_id == last_id or
                        now-self.received > 1.5 or now-self.last_view > 6 or now < next_run):
                    self.condition.wait(.1)
                    continue
                frame, frame_id, received, revision = self.frame, self.frame_id, self.received, self.revision
            started = time.monotonic()
            try:
                objects = detector.detect_objects(frame)
                error = None
            except Exception as exc:
                objects, error = {'people': [], 'vehicles': []}, str(exc)
            finished = time.monotonic()
            last_id = frame_id
            next_run = max(started + 1/self.detection_hz, finished + .05)
            with self.condition:
                if revision == self.revision and self.enabled:
                    self.people, self.vehicles = objects['people'], objects['vehicles']
                    self.result_frame, self.result_received = frame_id, received
                    self.inference_ms = (finished-started)*1000
                    self.inference_count += 1
                    self.detector_status = 'Detection ready' if error is None else 'Detection error: ' + error


def allowed_host(host):
    name = urlsplit('http://' + host).hostname
    if name in {'127.0.0.1', 'localhost', socket.gethostname(), socket.gethostname()+'.local', 'clockworkpi.local'}:
        return True
    try:
        address = ipaddress.ip_address(name)
        return any(address in network for network in (ipaddress.ip_network('10.0.0.0/8'),
                   ipaddress.ip_network('172.16.0.0/12'), ipaddress.ip_network('192.168.0.0/16'),
                   ipaddress.ip_network('169.254.0.0/16')))
    except (TypeError, ValueError):
        return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send(self, status, body, kind='application/json', extra=None):
        if isinstance(body, dict):
            body = json.dumps(body, separators=(',', ':')).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        for key, value in {'Content-Type': kind, 'Content-Length': len(body), 'Cache-Control': 'no-store',
                           'X-Content-Type-Options': 'nosniff', 'Cross-Origin-Resource-Policy': 'same-origin',
                           'Referrer-Policy': 'same-origin', 'Permissions-Policy': 'microphone=()',
                           **(extra or {})}.items():
            self.send_header(key, str(value))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def valid_host(self):
        try:
            return allowed_host(self.headers.get('Host', ''))
        except ValueError:
            return False

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, 'Open the uConsole camera address.', 'text/plain')
        url = urlsplit(self.path)
        if url.path in ('/health', '/api/state'):
            state = self.server.hub.snapshot()
            try:
                phone = json.loads((Path.home()/'.local/state/uconsole-camera/phone.json').read_text())
                state['phone_connected'] = bool(phone.get('connected') and time.time()-phone['updated'] < 30)
            except (OSError,ValueError,KeyError):
                state['phone_connected'] = False
            return self.send(200, state)
        if url.path == '/frame':
            try:
                after = int(parse_qs(url.query).get('after', ['0'])[0])
                frame, sequence, source, revision = self.server.hub.get_frame(after)
                return self.send(200, frame, 'image/jpeg', {'X-Frame-Id': sequence, 'X-Source': source,
                    'X-Revision': revision, 'X-Epoch': self.server.hub.epoch})
            except ValueError:
                return self.send(400, 'Invalid frame number', 'text/plain')
            except ConnectionError as exc:
                return self.send(503, str(exc), 'text/plain; charset=utf-8')
        relative = 'index.html' if url.path == '/' else url.path.lstrip('/')
        web = (ROOT/'web').resolve()
        path = (web/relative).resolve()
        if not path.is_relative_to(web) or not path.is_file():
            return self.send(404, 'Not found', 'text/plain')
        self.send(200, path.read_bytes(), mimetypes.guess_type(path)[0] or 'application/octet-stream')

    def do_POST(self):
        host = self.headers.get('Host', '')
        if not self.valid_host() or self.headers.get('Origin') != 'http://' + host:
            return self.send(403, 'Use the camera page to make changes.', 'text/plain')
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= length <= MAX_FRAME:
                raise ValueError('Invalid request size')
            self.connection.settimeout(5)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError('Incomplete request')
            if self.path == '/api/phone/open':
                if length:
                    raise ValueError('Unexpected request payload')
                try:
                    result = subprocess.run([sys.executable,str(ROOT/'phone_bridge.py'),'--open'],
                                            capture_output=True,text=True,timeout=20)
                except subprocess.TimeoutExpired:
                    return self.send(503, 'Phone did not respond. Check its connection.', 'text/plain')
                return self.send(200 if result.returncode == 0 else 503,
                                 result.stdout.strip() or result.stderr.strip(), 'text/plain')
            if self.path == '/api/control':
                if length > 1024 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Expected camera settings')
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError('Invalid camera settings')
                self.server.hub.control(data)
                return self.send(200, self.server.hub.snapshot())
            if self.path not in ('/phone/frame', '/phone/stop'):
                return self.send(404, 'Not found', 'text/plain')
            owner = str(uuid.UUID(self.headers.get('X-Publisher-Id', '')))
            if self.path == '/phone/stop':
                if length:
                    raise ValueError('Unexpected stop payload')
                self.server.hub.phone_stop(owner)
                return self.send(200, 'Stopped', 'text/plain')
            if self.headers.get('Content-Type') != 'image/jpeg' or not body.startswith(b'\xff\xd8') or not body.endswith(b'\xff\xd9'):
                raise ValueError('Expected a complete JPEG frame')
            self.server.hub.phone_publish(owner, body)
            self.send(200, 'OK', 'text/plain')
        except (ValueError, UnicodeError) as exc:
            self.send(400, str(exc), 'text/plain')
        except ConnectionError as exc:
            self.send(409, str(exc), 'text/plain')
        except OSError as exc:
            self.send(503, 'Camera request could not finish: '+str(exc), 'text/plain')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--home', default='esp32-cam.local')
    parser.add_argument('--home-fallback', default='', help='Optional ESP32 address if its hostname fails')
    parser.add_argument('--settings', type=Path, default=Path.home()/'.config/uconsole-camera/hub.json')
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--detection-hz', type=float, default=2)
    args = parser.parse_args()
    if not .2 <= args.detection_hz <= 5 or not 1 <= args.threads <= 4:
        parser.error('Choose 0.2–5 detections per second and 1–4 threads')
    targets = {'home': [f'http://{args.home}:81/stream'],
               'field': ['http://192.168.4.1:81/stream']}
    if args.home_fallback:
        targets['home'].append(f'http://{args.home_fallback}:81/stream')
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    server.hub = Hub(targets, args.settings, ROOT/'models/efficientdet_lite0.tflite', args.threads, args.detection_hz)
    print(f'uConsole camera hub ready on port {args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
