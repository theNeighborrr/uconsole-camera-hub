#!/usr/bin/env python3
"""View-only Android screen mirror using the pinned scrcpy server and FFplay."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
STATE = Path.home()/'.local/state/uconsole-drone-view'
SERVER_SHA256 = 'deacb991ed2509715160ffdc7907e47b4160eb30d1566217e9047fd5b8850cae'
VERSION = '4.1'


def adb(target, *args, timeout=12):
    result = subprocess.run(['adb', '-s', target, *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Android connection failed')
    return result.stdout.strip()


def paired_phone():
    config = json.loads((Path.home()/'.config/uconsole-camera/phone.json').read_text())
    status = json.loads((Path.home()/'.local/state/uconsole-camera/phone.json').read_text())
    if not status.get('connected') or time.time()-status.get('updated', 0)>30:
        raise RuntimeError('Unlock the Android phone, join the same Wi-Fi, and enable Wireless debugging. Then try again.')
    target = status['target']
    if adb(target, 'shell', 'getprop', 'ro.serialno') != config['serial']:
        raise RuntimeError('The connected phone does not match the paired phone.')
    return target


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)


def run(args):
    STATE.mkdir(parents=True, exist_ok=True)
    lock = (STATE/'mirror.lock').open('a')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise RuntimeError('Drone View is already open. Close its existing window first.')
    server_file = ROOT/'scrcpy-server-v4.1'
    if hashlib.sha256(server_file.read_bytes()).hexdigest() != SERVER_SHA256:
        raise RuntimeError('Screen-capture component did not pass verification.')
    target = paired_phone()
    scid = secrets.randbits(31)
    socket_name = f'scrcpy_{scid:08x}'
    remote_jar = f'/data/local/tmp/uconsole-drone-{scid:08x}.jar'
    port = None; connection = None; server = None; player = None; capture = None
    started = time.monotonic(); count = 0
    log_path = STATE/'last-session.log'
    report_path = STATE/'last-session.json'
    with log_path.open('w') as log:
        try:
            adb(target, 'push', str(server_file), remote_jar, timeout=30)
            port = int(adb(target, 'forward', 'tcp:0', 'localabstract:'+socket_name))
            options = [f'scid={scid:08x}', 'log_level=info', 'video=true', 'audio=false',
                       'control=false', 'clipboard_autosync=false', 'power_on=false',
                       'video_source=display', 'video_codec=h264', 'max_size=1024',
                       'video_bit_rate=2000000', f'max_fps={10 if args.mjpeg else 15}', 'tunnel_forward=true',
                       'raw_stream=true', 'send_dummy_byte=true']
            server = subprocess.Popen(['adb','-s',target,'shell','CLASSPATH='+remote_jar,
                'app_process','/','com.genymobile.scrcpy.Server',VERSION,*options],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
            # The one-byte greeting confirms the phone accepted this connection.
            deadline = time.monotonic()+15
            while time.monotonic()<deadline:
                if server.poll() is not None: raise RuntimeError('Phone screen capture stopped. Check '+str(log_path))
                try:
                    connection = socket.create_connection(('127.0.0.1',port),timeout=1)
                    if connection.recv(1) == b'\0': break
                except (OSError, TimeoutError): pass
                if connection: connection.close(); connection=None
                time.sleep(.15)
            else: raise RuntimeError('Phone did not start screen capture within 15 seconds.')
            connection.settimeout(1)
            if args.capture_seconds:
                capture = (STATE/'bench.h264').open('wb')
                sink = capture
            elif args.mjpeg:
                player = subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','warning',
                    '-threads','2','-probesize','32','-analyzeduration','0','-flags','low_delay',
                    '-f','h264','-i','pipe:0','-an','-fps_mode','passthrough','-c:v','mjpeg',
                    '-threads','2','-q:v','5','-flush_packets','1','-f','mpjpeg','pipe:1'],
                    stdin=subprocess.PIPE,stdout=sys.stdout.buffer,stderr=log)
                sink = player.stdin
            else:
                player = subprocess.Popen(['ffplay','-hide_banner','-loglevel','warning',
                    '-probesize','32','-analyzeduration','0','-flags','low_delay','-framedrop',
                    '-f','h264','-i','pipe:0','-an','-window_title','Drone View — view only · Q or Esc to close',
                    '-x','760','-y','390','-autoexit'],stdin=subprocess.PIPE,stdout=log,stderr=log)
                sink = player.stdin
            report = {'pid':os.getpid(),'started':time.time(),'view_only':True,'audio':False,
                      'server_version':VERSION,'player_pid':player.pid if player else None,
                      'max_size':1024,'max_fps':10 if args.mjpeg else 15,'bitrate':2000000}
            report_path.write_text(json.dumps(report,indent=2))
            received_at = None
            while not player or player.poll() is None:
                if args.capture_seconds and received_at and time.monotonic()-received_at>=args.capture_seconds: break
                try: chunk=connection.recv(65536)
                except socket.timeout:
                    if not received_at and time.monotonic()-started>30: raise RuntimeError('No screen video arrived.')
                    if server.poll() is not None: break
                    continue
                if not chunk: break
                if received_at is None: received_at=time.monotonic()
                count+=len(chunk)
                try: sink.write(chunk); sink.flush()
                except BrokenPipeError: break
            report.update({'ended':time.time(),'received_bytes':count,'video_seconds':round(time.monotonic()-received_at,2) if received_at else 0})
            report_path.write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2),file=sys.stderr if args.mjpeg else sys.stdout)
        finally:
            if connection: connection.close()
            if capture: capture.close()
            if player and player.stdin:
                try: player.stdin.close()
                except BrokenPipeError: pass
            stop(player)
            # Closing the video socket normally ends the phone server and its cleanup.
            if server:
                try: server.wait(timeout=4)
                except subprocess.TimeoutExpired: stop(server)
            if port is not None:
                try: adb(target,'forward','--remove','tcp:'+str(port))
                except Exception: pass
            try: adb(target,'shell','rm','-f',remote_jar)
            except Exception: pass
    if args.capture_seconds:
        if not count: raise RuntimeError('No screen frames received.')
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(STATE/'bench.h264'),
                        '-frames:v','1',str(STATE/'bench.jpg')],check=True,timeout=20)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capture-seconds',type=float,default=0)
    parser.add_argument('--mjpeg',action='store_true',help='Send view-only frames to the local camera hub')
    args=parser.parse_args()
    if not 0<=args.capture_seconds<=20:parser.error('Capture must be between 0 and 20 seconds.')
    if args.mjpeg and args.capture_seconds:parser.error('Choose capture or hub output, not both.')
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try: run(args)
    except KeyboardInterrupt: return
    except Exception as exc:
        message=str(exc)
        print(message,file=sys.stderr)
        if not args.capture_seconds and not args.mjpeg and os.environ.get('DISPLAY'):
            subprocess.run(['zenity','--error','--title=Drone View','--text='+message],timeout=120)
        raise SystemExit(1)


if __name__=='__main__': main()
