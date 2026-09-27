"""One bounded Ring stream, with user-private credentials and no saved images."""
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time

from stream import jpeg_frames

RING_CAMERAS = {'ring_back': 'Back', 'ring_side': 'Side', 'ring_front': 'Front Door'}
RING_LIMITS = {'ring_back': 300, 'ring_side': 300, 'ring_front': 120}


class RingFeed:
    def __init__(self, source):
        import fcntl
        if source not in RING_CAMERAS:
            raise ValueError('Unknown Ring camera')
        app = Path.home()/'.local/share/uconsole-ring'
        config = Path.home()/'.config/uconsole-ring'
        if not (config/'auth.json').is_file():
            raise ConnectionError('Open Connect Ring on the uConsole and sign in first.')
        self.lock = (config/'connection.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise ConnectionError('Another Ring connection is finishing. Try Start live view again shortly.')
        self.frames = queue.Queue(maxsize=1)
        self.finished = threading.Event()
        self.started = self.last_frame = time.monotonic()
        self.received = False
        self.error = ''
        try:
            node = json.loads((app/'runtime.json').read_text())['node']
            self.process = subprocess.Popen(
                [node, str(app/'client.mjs'), 'stream', RING_CAMERAS[source], str(RING_LIMITS[source])],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True)
        except BaseException:
            self.lock.close()
            raise
        self.reader = threading.Thread(target=self.read, name='ring-frames', daemon=True)
        self.errors = threading.Thread(target=self.read_errors, name='ring-status', daemon=True)
        self.reader.start()
        self.errors.start()

    def read(self):
        try:
            for frame in jpeg_frames(self.process.stdout):
                item = (time.monotonic(), frame)
                try:
                    self.frames.put_nowait(item)
                except queue.Full:
                    try:
                        self.frames.get_nowait()
                    except queue.Empty:
                        pass
                    self.frames.put_nowait(item)
        except (OSError, ValueError):
            self.error = 'Ring video was interrupted. Try Start live view again.'
        finally:
            self.finished.set()

    def read_errors(self):
        # Only forward the connector's fixed public messages, never API diagnostics.
        allowed = {'Connect Ring first.', 'That Ring camera name was not found uniquely.',
                   'This camera is offline in Ring.', 'Ring connection timed out.',
                   'Ring connection failed. Check sign-in and internet access.', 'Ring connection failed.'}
        for line in iter(self.process.stderr.readline, b''):
            text = line.decode(errors='replace').strip()
            if text in allowed:
                self.error = text

    def next_frame(self):
        try:
            when, frame = self.frames.get(timeout=.25)
            if time.monotonic()-when > 2:
                return None
            self.last_frame, self.received = when, True
            return frame
        except queue.Empty:
            if self.finished.is_set():
                raise ConnectionError(self.error or 'Ring live view ended. Press Start live view to reconnect.')
            if time.monotonic()-self.last_frame > (12 if self.received else 40):
                raise ConnectionError('Ring is not sending video. Check its Live View and internet connection, then try again.')
            return None

    def close(self):
        try:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=3)
            self.reader.join(timeout=2)
            self.errors.join(timeout=2)
            if self.reader.is_alive() or self.errors.is_alive():
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.reader.join(timeout=1)
                self.errors.join(timeout=1)
            self.process.stdout.close()
            self.process.stderr.close()
        finally:
            self.lock.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
