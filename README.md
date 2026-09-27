# uConsole Camera Hub

One camera source, one detector, and a shared live view on the uConsole, PC, and phone. The uConsole hosts the application; a PC is not required for everyday viewing.

This is the initial source import from a working Raspberry Pi CM4 / Debian 13 ARM64 installation. It is a development snapshot, not a universal one-click installer.

## Sources and controls

- ESP32-CAM: home Wi-Fi or its own hotspot, using the camera's MJPEG endpoint.
- Android: phone-camera publishing through a paired ADB connection.
- Drone: a view-only copy of the paired Android's PotensicPro screen. The normal controller and phone remain the flight interface.
- Ring: three on-demand sources using a community connector. Internet is required.
- Shared camera selection and Detection switch; browser-local People/Vehicles filters and confidence threshold behind **Filters**.
- Green people boxes and yellow car/truck/bus/motorcycle boxes. The Possible police option is disabled; no custom police or Flock model is installed.

## Start here

Read [manual setup](docs/SETUP.md), [everyday use](docs/USAGE.md), and [validation and limitations](docs/STATUS.md). Camera and radio applications are separate: [uConsole Radio](https://github.com/theNeighborrr/uconsole-radio) can launch this viewer at `http://127.0.0.1:8765/`.

The dashboard uses HTTP port 8765 and has no viewer login. Use a trusted local network; anyone who can reach it can view and change the shared source. This project does not configure remote internet access.

## Development

```sh
python3 tests/check_ring_sessions.py
```

This uses a fake Ring source and does not contact Ring, read account credentials, or require a detection model. The original installation also passed live and browser checks described in the status guide. Fresh installation and all optional connector setup steps have not yet been tested on a second device.

No account files, private camera footage, device keys, training data, pretrained binaries, or private field-kit documents are included. Model/component downloads retain their upstream licenses; see [third-party components](THIRD_PARTY.md). A license for the project's own code has not yet been selected.
