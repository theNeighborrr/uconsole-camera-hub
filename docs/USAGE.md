# Everyday camera use

Open `http://UCONSOLE_HOST:8765/` from another device on the same network, replacing `UCONSOLE_HOST` with the uConsole hostname or address. On the uConsole itself, open `http://127.0.0.1:8765/`. Use HTTP. Camera source and Detection affect all viewers. Only one camera source is shared at a time.

Open **Filters** for green People boxes, yellow Vehicles boxes, and Confidence. People/Vehicles visibility is remembered in each browser. Closing Filters leaves them active. Possible police remains disabled. Generic vehicle boxes do not distinguish police cars. The detector can miss objects or produce false boxes, including stationary vehicles.

## ESP32

Select Home Wi-Fi when the camera and uConsole share a network. Close direct camera stream tabs so the hub can use the camera's upstream connection. For Hotspot, join the camera's hotspot first and then select ESP32 Hotspot. The selector does not change the uConsole's Wi-Fi network. Other viewers need a network path to the uConsole. Hotspot mode uses `192.168.4.1:81/stream` in this snapshot.

## Android camera

Select Android phone, choose Open phone camera, and tap Start camera on the phone. Keep its publishing page visible and the phone unlocked. It uses `http://127.0.0.1:8765/phone.html` on the paired phone, forwarded to the uConsole by ADB. A phone used only as a viewer needs no ADB pairing.

## Drone

Connect Android to the drone controller by USB. Keep Android and the uConsole on shared Wi-Fi with Wireless debugging enabled, and keep the live picture visible in PotensicPro. Select Drone in the hub. The complete Android screen is mirrored, with no audio or flight-control channel. Use another device to watch; switching the sending Android away from PotensicPro changes what is captured.

## Ring

The initial snapshot expects uniquely named Ring cameras **Back**, **Side**, and **Front Door**. These aliases are currently set in `ring_feed.py`, `connectors/ring/client.mjs`, and the selector in `web/index.html`. Configuration through the UI remains future work.

Selecting a different Ring source starts its shared live session. Back and Side allow up to five minutes; Front Door allows two. Start live view opens another session after expiry, failure, or a pause. Stop affects all viewers. Switching sources or closing/hiding all viewers stops Ring after a short delay. A saved Ring source stays paused after restarting the hub; sessions never renew automatically.

Ring requires internet. Live viewing uses battery and can affect motion alerts; Ring may record Live View according to account settings. The hub itself uses video only and saves no footage. Use the Ring app for audio, history, and camera settings.

## Recovery

Check source, camera power, HTTP address, and shared network first. If a foreground hub stops, read its terminal error and restart the same command. Optional services and backups are deployment-specific in this initial import. Before updating an installed copy, save its code and local configuration separately; do not commit private account files. Updating these repositories does not automatically update an installed uConsole.
