"""One on-demand, view-only Android screen stream for all camera hub viewers."""
from pathlib import Path
import os
import queue
import signal
import subprocess
import threading
import time

from stream import jpeg_frames


class DroneFeed:
    def __init__(self):
        self.frames = queue.Queue(maxsize=1)
        self.finished = threading.Event()
        self.error = None
        self.started = self.last_frame = time.monotonic()
        self.received = False
        path = Path.home()/'.local/share/uconsole-drone-view/mirror.py'
        state = Path.home()/'.local/state/uconsole-drone-view'
        state.mkdir(parents=True, exist_ok=True)
        self.log = (state/'hub.log').open('w')
        try:
            self.process = subprocess.Popen(['/usr/bin/python3',str(path),'--mjpeg'],
                stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=self.log,start_new_session=True)
        except BaseException:
            self.log.close()
            raise
        self.reader = threading.Thread(target=self.read, name='drone-frames', daemon=True)
        self.reader.start()

    def read(self):
        try:
            for frame in jpeg_frames(self.process.stdout):
                item = (time.monotonic(), frame)
                try: self.frames.put_nowait(item)
                except queue.Full:
                    try: self.frames.get_nowait()
                    except queue.Empty: pass
                    self.frames.put_nowait(item)
        except (OSError, ValueError) as exc:
            self.error = str(exc)
        finally:
            self.finished.set()

    def next_frame(self):
        try:
            when, frame = self.frames.get(timeout=.5)
            if time.monotonic()-when > 2: return None
            self.last_frame = when
            self.received = True
            return frame
        except queue.Empty:
            if self.finished.is_set():
                raise ConnectionError('Drone screen stopped. Keep PotensicPro visible on the paired Android; check Wi-Fi and Wireless debugging.')
            limit = 8 if self.received else 30
            if time.monotonic()-self.last_frame > limit:
                raise ConnectionError('Waiting for the Android drone screen. Check the phone connection and keep PotensicPro visible.')
            return None

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try: self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=5)
        self.reader.join(timeout=2)
        self.process.stdout.close()
        self.log.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
