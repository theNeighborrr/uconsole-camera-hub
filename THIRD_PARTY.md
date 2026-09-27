# Third-party components

External dependencies retain their upstream licenses; they are not relicensed by this source snapshot.

- EfficientDet-Lite0 / TensorFlow model: the pinned URL and checksum are in `models/PROVENANCE.md`; the binary is downloaded separately.
- Google LiteRT, NumPy, Pillow, and Zeroconf: Python dependencies; the tested direct versions are in `requirements.txt`.
- Ring community client: [ring-client-api](https://github.com/dgreif/ring/tree/main/packages/ring-client-api), pinned at 14.3.0 with its dependency lockfile. This is not an official Ring integration.
- Node.js: runtime installed separately; the original installation used Node 24.21.0 ARM64.
- [scrcpy](https://github.com/Genymobile/scrcpy): optional Android server 4.1, downloaded separately and verified by the screen adapter.
- FFmpeg, ADB, and Debian system packages: installed separately and governed by their distribution licenses.

No upstream model weights, scrcpy binary, Node runtime, FFmpeg binary, proprietary drone app, or private camera image is bundled in this repository.
