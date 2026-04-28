# tofnet

A small cluster of Seeed XIAO ESP32-C3 boards streaming time-of-flight distance
measurements to a PC over BLE.

## Architecture

- **3 sensor nodes** (XIAO ESP32-C3) — each runs the same Arduino sketch
  parameterized by `NODE_ID`. Each node is an independent BLE peripheral that
  advertises as `tofnet-N` and exposes a single distance characteristic with
  notify.
- **PC receiver** — a Python script using [`bleak`](https://github.com/hbldh/bleak)
  that scans for `tofnet-*` peripherals, connects to all of them in parallel,
  and subscribes to distance notifications.

No router, hotspot, or extra hardware bridge needed — every modern laptop
already has BLE.

## Repo layout

```
firmware/tofnet_node/tofnet_node.ino   Arduino sketch for the sensor nodes
pc/receiver.py                         PC-side BLE aggregator
pc/requirements.txt                    Python dependencies
```

## Flashing the nodes

1. Install the Arduino IDE and add the **ESP32 board package** (Boards Manager →
   search "esp32" by Espressif).
2. Select board: **XIAO_ESP32C3**.
3. Open `firmware/tofnet_node/tofnet_node.ino`.
4. Set `#define NODE_ID 1` (or `2`, `3`) at the top.
5. Flash. Repeat for the other two chips with `NODE_ID 2` and `NODE_ID 3`.
6. Label each chip with its number — saves a lot of confusion on stage day.

The sketch ships with a fake distance generator so you can verify the BLE
pipeline before the ToF sensor is wired up. Replace `readDistanceMm()` with the
real sensor read once the hardware is in place (see the TODO comment).

## Running the PC receiver

```bash
cd pc
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
python receiver.py
```

Expected output:

```
scanning 10.0s for tofnet-* peripherals...
found 3 node(s): tofnet-1, tofnet-2, tofnet-3
connected: tofnet-1 (XX:XX:XX:XX:XX:XX)
connected: tofnet-2 (XX:XX:XX:XX:XX:XX)
connected: tofnet-3 (XX:XX:XX:XX:XX:XX)
[14:32:01.420] tofnet-1: 1234 mm
[14:32:01.610] tofnet-2: 2876 mm
...
```

## Protocol

| Field      | UUID                                   | Type         | Notes                            |
|------------|----------------------------------------|--------------|----------------------------------|
| Service    | `c91a1000-7bf3-4f6e-9e1a-8d4b6f1c2a01` |              | tofnet service                   |
| Distance   | `c91a1001-7bf3-4f6e-9e1a-8d4b6f1c2a01` | `uint32` LE  | mm; READ + NOTIFY; pushed every 5 s |

Node identity is carried in the BLE device name (`tofnet-1` … `tofnet-3`), not
in the payload — saves bytes and keeps the characteristic dead simple.

## Pre-show checklist

- **Attach the external antenna to each XIAO.** The Seeed XIAO ESP32-C3 ships
  configured to use the IPEX connector — without an antenna attached the BLE
  signal is barely usable (RSSI ~-85 at desk distance). With the antenna,
  RSSI is ~-45 at the same distance.
- Verify the PC's BLE adapter works (Device Manager → Bluetooth, or a quick
  `bleak` scan). Some older or aftermarket WiFi cards lack BLE.
- If a node was advertising under a different name previously, **toggle
  Bluetooth off/on in Windows Settings** before testing — Windows aggressively
  caches BLE advertisement data.
- Dry-run the full kit in the actual venue if possible.
- Bring a spare flashed XIAO in case one chip fails.
- Charge / power-bank the nodes — BLE is low-power but a dead battery is a dead node.
