"""tofnet PC receiver.

Continuously scans for BLE peripherals named "tofnet-*". As soon as one is
detected, kicks off a connection so notifications start flowing immediately —
no waiting on a fixed scan window. Late-arriving or power-cycled nodes are
picked up automatically. Reconnects on drop.
"""
import asyncio
import struct
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

DISTANCE_CHAR_UUID = "c91a1001-7bf3-4f6e-9e1a-8d4b6f1c2a01"
NAME_PREFIX = "tofnet-"
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
    tasks: dict[str, asyncio.Task] = {}

    def on_detect(device: BLEDevice, adv: AdvertisementData) -> None:
        name = device.name or adv.local_name or ""
        if not name.startswith(NAME_PREFIX) or device.address in tasks:
            return
        print(f"detected: {name} ({device.address}) rssi={adv.rssi}")
        tasks[device.address] = asyncio.create_task(manage_node(device, name))

    print(f"scanning continuously for {NAME_PREFIX}* peripherals (Ctrl+C to stop)...")
    async with BleakScanner(detection_callback=on_detect):
        await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye")
