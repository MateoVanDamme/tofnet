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
- **Dashboard** — a tkinter GUI that shows the live distances and turns them
  into a sound cue for the art exhibition. It launches the receiver as a child
  process and parses its output, so the receiver stays untouched and remains the
  only thing connected to the nodes.

No router, hotspot, or extra hardware bridge — every modern laptop has BLE.

## Repo layout

```
firmware/tofnet_node_sensor/tofnet_node_sensor.ino   Arduino sketch — real TF-Luna sensor (use this)
firmware/tofnet_node/tofnet_node.ino                 Arduino sketch — fake generator, BLE pipeline testing only
pc/dashboard.py                                      tkinter dashboard + sound playback (the exhibition app)
pc/receiver.py                                        PC-side BLE aggregator
pc/scan_all.py                                        BLE scan helper
pc/sounds/                                            <code>.wav files played by the dashboard (you create this)
pc/requirements.txt                                   Python dependencies
```

Both sketches expose the identical BLE protocol and advertise as `tofnet-N`;
they differ only in `readDistanceMm()`. **For a real demo, flash
`tofnet_node_sensor`** — it reads an actual TF-Luna LiDAR over I2C.
`tofnet_node` returns a fake sweeping value and exists only to test the BLE
pipeline before sensors are wired up.

## Flashing the nodes

1. Install the Arduino IDE and add the **ESP32 board package** (Boards Manager →
   search "esp32" by Espressif).
2. Select board: **XIAO_ESP32C3**.
3. Open `firmware/tofnet_node_sensor/tofnet_node_sensor.ino` (the real-sensor
   sketch). Wire the TF-Luna first: SDA → D4 (GPIO 6), SCL → D5 (GPIO 7), 5V,
   GND, and the mode pin → D6 (GPIO 21) so it's held LOW at boot for I2C.
4. Set `#define NODE_ID N` at the top — must be unique per chip.
5. Flash. Repeat for each chip with the next `NODE_ID`.
6. Label each chip with its number.

To test the BLE pipeline **without** a sensor wired up, flash
`firmware/tofnet_node/tofnet_node.ino` instead — it ships with a fake distance
generator (a sweeping value) and exposes the identical BLE protocol.

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

## Dashboard (the exhibition app)

```bash
cd pc
python dashboard.py     # needs tkinter (stdlib), bleak, and pygame (requirements.txt)
```

The dashboard launches `receiver.py` for you, so **do not run `receiver.py`
separately at the same time** — a BLE peripheral only accepts one central
connection, and the two would fight over the nodes.

What it shows, per node, in a card: the character, the live distance, status
(live / stale / waiting / "no valid sensor reading"), and a zone control. A live
log pane at the bottom mirrors the receiver's output.

### Characters and the sound code

Each node maps to a story character. The dashboard continuously builds a sound
name by concatenating `<marker><zone>` for every node (shown live), and the
**▶ Play** button plays the matching file from `sounds/`.

| Node | Marker | Character     |
|------|--------|---------------|
| 1    | `P`    | Prince        |
| 2    | `Q`    | Queen         |
| 3    | `K`    | King          |
| 4    | `M`    | Mobat (priest)|

The distance is bucketed into **4 zones** (1 = closest .. 4 = farthest), which
encode how important that character is in the story. A failed / out-of-range
reading (`0 mm`) counts as zone 4. With 4 nodes that's `4⁴ = 256` possible
codes, e.g. `P1Q3K2M4`. Default zone boundaries are 2 m / 4 m / 6 m — edit
`ZONE_EDGES_M` in `dashboard.py` to reshape them.

Put one sound file per code you intend to use in `pc/sounds/`, named exactly
like the code. Playback uses [`pygame`](https://www.pygame.org), so `.wav`,
`.ogg`, and `.mp3` all work (MP3 is the sane choice for full-length songs) — the
dashboard looks for `<code>.wav`, then `.ogg`, then `.mp3`, e.g.
`pc/sounds/P1Q3K2M4.mp3`. A missing file is reported in the log instead of
crashing.

The single **▶ Play / ■ Stop** button toggles playback of the current code; it
flips back to Play on its own when a track finishes. A 30 s test tone ships at
`pc/sounds/P1Q1K1M1.wav` — set all four zone dropdowns to `1` and hit Play to
hear it.

### Manual override

Each card has a zone dropdown — **Auto** (follow the sensor) or a pinned value
**1–4** — independent per node. Pinned nodes show their `→ zone` in orange, and
the big code turns orange whenever any node is off Auto, so an override is never
silently left on. This is the safety fallback if a sensor misbehaves mid-show.

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
