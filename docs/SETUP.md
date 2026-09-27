# Manual setup — development snapshot

The original application runs on Debian 13 ARM64 with Python 3.13 on a Raspberry Pi CM4. These generalized setup steps still need a fresh-device test. This initial import does not provide an automatic migration or rollback installer. Preserve a working installation before replacing any files; the steps below are for a new setup.

## ESP32 viewer and detector

The camera needs an MJPEG stream at `http://CAMERA_HOST:81/stream`. Camera firmware, its Wi-Fi credentials, and programming tools are not included. Have the uConsole and ESP32 on the same network and close direct ESP32 stream tabs.

Install Debian's Python virtual-environment support if it is absent:

```sh
sudo apt install python3-venv
```

From the root of this repository:

```sh
python3 tools/fetch_model.py
app_dir="$HOME/.local/share/uconsole-camera-hub"
mkdir -p "$app_dir/models"
cp server.py detector.py stream.py phone_bridge.py drone.py ring_feed.py requirements.txt "$app_dir/"
cp -R web "$app_dir/"
cp models/efficientdet_lite0.tflite "$app_dir/models/"
python3 -m venv "$app_dir/.venv"
"$app_dir/.venv/bin/python" -m pip install -r "$app_dir/requirements.txt"
"$app_dir/.venv/bin/python" "$app_dir/server.py" --home YOUR_ESP32_HOSTNAME
```

Replace `YOUR_ESP32_HOSTNAME` with the camera's actual hostname or address. `--home-fallback` accepts an optional second address. The default hostname is the generic `esp32-cam.local`; this repo contains no original home-network fallback address. For the usual ESP32 hotspot, the Field source uses `192.168.4.1`.

Leave the terminal running, then open `http://127.0.0.1:8765/` on the uConsole or `http://UCONSOLE_HOST:8765/` from a same-network browser. Ctrl+C stops this foreground server. User-service startup and desktop integration can be added after the foreground setup works; no service is installed by these commands.

The hub binds to the local network by default and has no login. Use `--bind 127.0.0.1` if you want access only on the uConsole. Do not forward the HTTP port onto the internet.

## Optional Android connection

Install `adb`, enable Developer options / USB debugging on Android, and pair this uConsole through USB authorization or Wireless debugging. Wireless pairing uses the phone's pairing-code dialog and its pairing address; the later connection address can have a different port.

Create a private configuration at `~/.config/uconsole-camera/phone.json` with your phone's actual ADB serial number:

```json
{"serial":"YOUR_PHONE_SERIAL"}
```

The helper verifies the phone's `ro.serialno` and discovers its wireless connection endpoint. Set directory permissions to 700 and the file to 600. Never commit this file or ADB keys. Then, in a second terminal, run:

```sh
"$HOME/.local/share/uconsole-camera-hub/.venv/bin/python" "$HOME/.local/share/uconsole-camera-hub/phone_bridge.py"
```

Select Android phone in the viewer and choose Open phone camera. Tap Start camera on Android. The publishing page needs the forwarded localhost URL; opening the normal LAN viewer is not a substitute. See [everyday use](USAGE.md).

## Optional Android drone screen

This uses the same paired-phone helper. Install FFmpeg separately, then place `connectors/drone/mirror.py` in `~/.local/share/uconsole-drone-view/`. Download the official [scrcpy 4.1 server](https://github.com/Genymobile/scrcpy/releases/tag/v4.1) into that folder as `scrcpy-server-v4.1`.

The adapter checks SHA-256 `deacb991ed2509715160ffdc7907e47b4160eb30d1566217e9047fd5b8850cae` before using the server. If it differs, stop and resolve the version/source mismatch; do not remove the check. The binary is not bundled here.

Keep the controller connected to Android by USB and Android connected to the uConsole over Wi-Fi. Keep the live picture visible in PotensicPro, then select Drone in the hub. This supplies a delayed, view-only preview with no flight controls or audio.

## Optional Ring connector

Install a compatible Node.js runtime and FFmpeg separately. The original verified runtime was Node 24.21.0 ARM64 with FFmpeg 7.1.5. Copy the connector source to its expected path:

```sh
ring_dir="$HOME/.local/share/uconsole-ring"
mkdir -p "$ring_dir"
cp connectors/ring/client.mjs connectors/ring/sign-in.py connectors/ring/package.json connectors/ring/package-lock.json "$ring_dir/"
cd "$ring_dir"
npm ci --ignore-scripts --omit=dev --omit=optional --no-audit --no-fund
python3 - <<'PY'
import json
from pathlib import Path
import shutil
node = shutil.which('node')
if not node:
    raise SystemExit('Install Node.js first.')
Path('runtime.json').write_text(json.dumps({'node': node}))
PY
python3 sign-in.py
```

Enter your own credentials in that local terminal. The password is not saved; a private refresh token is stored outside the web folder under `~/.config/uconsole-ring/`. Do not print or commit it. Existing sign-in tokens are retained; the initial helper is not yet a reauthentication/settings manager.

This snapshot matches cameras named **Back**, **Side**, and **Front Door**. See [the current alias limitation](USAGE.md). Ring is an internet-dependent community integration and can break when its upstream service changes. Start with one short live session and confirm clean Stop behavior before everyday use.
