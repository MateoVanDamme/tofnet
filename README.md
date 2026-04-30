# tofnet

Seeed XIAO ESP32-C3 nodes streaming time-of-flight distance measurements to a
PC over BLE.

## Architecture

- **Sensor nodes** (XIAO ESP32-C3) — each runs the same Arduino sketch
  parameterized by `NODE_ID`. Each node is a BLE peripheral advertising as
  `tofnet-N` with a single distance characteristic (NOTIFY).
- **PC receiver** — Python script using [`bleak`](https://github.com/hbldh/bleak)
  that scans continuously for `tofnet-*` peripherals, connects as they appear,
  and reconnects on drop. Works for any number of nodes.

No router, hotspot, or extra hardware bridge — every modern laptop has BLE.

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
4. Set `#define NODE_ID N` at the top — must be unique per chip.
5. Flash. Repeat for each chip with the next `NODE_ID`.
6. Label each chip with its number.

The sketch ships with a fake distance generator so the BLE pipeline can be
tested end-to-end before the ToF sensor is wired up. Replace `readDistanceMm()`
with the real sensor read (see TODO in the sketch).

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
scanning continuously for tofnet-* peripherals (Ctrl+C to stop)...
detected: tofnet-1 (XX:XX:XX:XX:XX:XX) rssi=-47
connected: tofnet-1 (XX:XX:XX:XX:XX:XX)
[14:32:01.420] tofnet-1: 1234 mm
[14:32:01.610] tofnet-2: 2876 mm
...
```

## Protocol

| Field      | UUID                                   | Type         | Notes                            |
|------------|----------------------------------------|--------------|----------------------------------|
| Service    | `c91a1000-7bf3-4f6e-9e1a-8d4b6f1c2a01` |              | tofnet service                   |
| Distance   | `c91a1001-7bf3-4f6e-9e1a-8d4b6f1c2a01` | `uint32` LE  | mm; READ + NOTIFY; pushed every 5 s |

Node identity is carried in the BLE device name (`tofnet-N`), not in the
payload — keeps the characteristic dead simple.

## Pre-show checklist

- **Attach the external antenna to each XIAO.** The XIAO ESP32-C3 ships
  configured for the IPEX connector — without an antenna, RSSI is ~-85 at desk
  distance vs. ~-45 with one.
- Verify the PC's BLE adapter works (Device Manager, or a quick `bleak` scan).
  Some older or aftermarket WiFi cards lack BLE.
- If a node previously advertised under a different name, **toggle Bluetooth
  off/on in Windows Settings** — Windows aggressively caches advertisement data.
- Dry-run the full kit in the actual venue if possible.
- Bring a spare flashed XIAO.
- Charge / power-bank the nodes.

## Credits

The TF-Luna I2C read logic in `firmware/tofnet_node_sensor/` (trigger packet,
9-byte frame parsing) is adapted from DroneBot Workshop's TF-Luna LiDAR
tutorial: <https://dronebotworkshop.com/tf-luna-lidar/>.

The page does not state an explicit license and the site's Terms of Use is
silent on code reuse — if you plan to redistribute or use this in a product,
contact DroneBot Workshop for clarification.
