"""Debug helper: list every BLE device seen during a 10-second scan.

Use this to confirm the tofnet chips are advertising at all, and under what
name. If you see a device at the chip's MAC but with an empty/None name,
the sketch isn't including the name in the advertising packet.
"""
import asyncio

from bleak import BleakScanner


async def main() -> None:
    print("scanning 10s for ALL BLE devices...")
    devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
    if not devices:
        print("nothing seen — check the PC's BLE adapter")
        return
    for address, (device, adv) in devices.items():
        name = device.name or adv.local_name or "<no name>"
        services = ", ".join(adv.service_uuids) if adv.service_uuids else "-"
        print(f"  {address}  rssi={adv.rssi:>4}  name={name!r}  services=[{services}]")


if __name__ == "__main__":
    asyncio.run(main())
