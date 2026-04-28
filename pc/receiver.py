"""tofnet PC receiver.

Scans for BLE peripherals named "tofnet-*", connects to all of them in
parallel, and prints distance notifications as they arrive. Reconnects
automatically if a node drops.
"""
import asyncio
import struct
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

DISTANCE_CHAR_UUID = "c91a1001-7bf3-4f6e-9e1a-8d4b6f1c2a01"
NAME_PREFIX = "tofnet-"
SCAN_TIMEOUT_S = 20.0
RECONNECT_DELAY_S = 3.0


def make_handler(node_name: str):
    def handler(_sender, data: bytearray) -> None:
        (distance_mm,) = struct.unpack("<I", data)
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}] {node_name}: {distance_mm} mm")
    return handler


async def manage_node(device: BLEDevice, name: str) -> None:
    """Stay connected to one node, reconnect on drop."""
    while True:
        try:
            async with BleakClient(device) as client:
                print(f"connected: {name} ({device.address})")
                await client.start_notify(DISTANCE_CHAR_UUID, make_handler(name))
                while client.is_connected:
                    await asyncio.sleep(1.0)
                print(f"disconnected: {name}")
        except Exception as e:
            print(f"error on {name}: {e}; retrying in {RECONNECT_DELAY_S}s")
            await asyncio.sleep(RECONNECT_DELAY_S)


async def main() -> None:
    print(f"scanning {SCAN_TIMEOUT_S}s for {NAME_PREFIX}* peripherals...")
    # On Windows, device.name is frequently empty even when the peripheral
    # advertises a local name — read the adv data and use whichever is set.
    seen = await BleakScanner.discover(timeout=SCAN_TIMEOUT_S, return_adv=True)
    nodes: list[tuple[BLEDevice, str]] = []
    for _, (device, adv) in seen.items():
        name = device.name or adv.local_name or ""
        if name.startswith(NAME_PREFIX):
            nodes.append((device, name))

    if not nodes:
        print("no tofnet nodes found — check the chips are powered and advertising")
        return

    print(f"found {len(nodes)} node(s): {', '.join(n for _, n in nodes)}")
    await asyncio.gather(*(manage_node(d, n) for d, n in nodes))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye")
