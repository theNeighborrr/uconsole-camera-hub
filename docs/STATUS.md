# Validation and known limitations

Imported September 27, 2026 from hub version 5 on a Raspberry Pi CM4 with Debian 13 ARM64. The imported application files matched the installed copies before replacing the original ESP32 hostname/address defaults with generic defaults. The uConsole installation was not changed by this repository preparation.

The prepared import passed its Ring-session state checks using a fake feed, including all six feed instances closing and no overlap. Python and JavaScript syntax, JSON data, local documentation links, and checks for private credentials/device data also passed. These are import checks; they do not substitute for a fresh-device installation test.

Confirmed on that installation:

- Shared ESP32 and Android video, one native EfficientDet-Lite0 detector, and synchronized source/Detection controls.
- Actual PotensicPro screen delivery with concurrent browser viewers. Flight-height accuracy and preview latency were not established.
- Live Back, Side, and Front Door Ring delivery with two shared browser viewers, shared Stop, and idle shutdown.
- Ring session state checks for expiry, errors, no automatic renewal, restart-paused behavior, and at most one Ring stream.
- People/vehicle filters, stale-box clearing, phone capture without audio, and browser controls at uConsole and phone viewport sizes.

The final Ring Back sample advanced 106 video frames and 27 inferences over 15 seconds. These short samples are not guaranteed performance or a sustained camera-plus-heavy-SDR benchmark. A cold boot and a fresh installation on a second device remain unverified.

## Side camera recognition

The user observed missing boxes around parked vehicles in an elevated, grayscale Side view. Detection was running with fresh results, but the model returned no retained objects. A lighting check did not visibly resolve the problem. Cropping and an existing generic alternative model did not reliably recover the nearer obstructed vehicle. No production change was made from those experiments.

A Front Door screenshot subsequently showed a car box at 61% model confidence in night vision. This establishes that detection and overlay display work for that view; it does not establish an accuracy percentage. Camera angle, obstruction, scale, and lighting may all affect recognition. Parked vehicles do not need to move to be detected. Private diagnostic images and datasets are excluded from this repository.

## Next work

- Exercise the manual setup on another uConsole before claiming a reproducible installer.
- Make Ring aliases and connector setup configurable without source edits.
- Add portable browser fixtures and integration checks to this repo.
- Evaluate representative day/night views before changing the detector or adding model workload.
- Keep police recognition disabled until independently evaluated accuracy supports enabling it.
