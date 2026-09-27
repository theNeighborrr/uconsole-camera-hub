"""Download the exact model expected by detector.py; never overwrite an unknown file."""
import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen

URL = 'https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/object_detection/rpi/lite-model_efficientdet_lite0_detection_metadata_1.tflite'
EXPECTED = '2e04c53bfeac0ac2a30c057c7e2a777594ce39baaac35a92f74fb1e8c4fc4e0b'
destination = Path(__file__).resolve().parents[1] / 'models/efficientdet_lite0.tflite'

def main():
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != EXPECTED:
            raise SystemExit('An existing model has a different checksum; leaving it unchanged.')
        print('Expected model already present.')
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            total = 0
            with urlopen(URL, timeout=30) as source:
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > 50 * 1024 * 1024:
                        raise ValueError('Unexpectedly large model download')
                    output.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != EXPECTED:
            raise ValueError('Model checksum did not match; download discarded')
        # Keep an existing file if another download completed concurrently.
        with destination.open('xb') as target:
            target.write(temporary.read_bytes())
        print('Verified model saved to ' + str(destination))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

if __name__ == '__main__':
    main()
