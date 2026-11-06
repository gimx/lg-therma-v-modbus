#!/usr/bin/env python3

"""Query an LG Therma V heat pump or an SDM120 meter and print every value."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from modbus_connection import ModbusError
from modbus_connection.cli_helper import (
    CountingUnit,
    add_connection_args,
    connect_from_args,
    print_component,
)
from modbus_connection.model import Component

from lg_therma_v_modbus import Sdm120, ThermaV

# The RS-485 line, direct or through a socket:// device, and the gateways
# answering Modbus TCP themselves. No ASCII: the library does not support it.
CONNECTIONS = (("tcp", None), ("serial", "rtu"))

EXAMPLES = """examples:
  # a USB or serial adapter, heat pump on unit 1
  uv run script/query.py /dev/ttyUSB0 --transport serial --unit 1
  # the meter on the same line
  uv run script/query.py /dev/ttyUSB0 --transport serial --unit 2 --meter
  # a box forwarding the RTU frames over TCP
  uv run script/query.py socket://192.168.1.50:8899 --transport serial --unit 1
  # a gateway answering Modbus TCP, with every register read
  uv run script/query.py 192.168.1.60 --port 502 --unit 1 --raw
  # a heat pump from December 2023 or later
  uv run script/query.py /dev/ttyUSB0 --transport serial --december-2023
"""


def served_components(device: ThermaV | Sdm120) -> list[tuple[str, Component]]:
    """The components a poll reads, by attribute name."""
    names = (
        "status",
        "readings",
        "water_pressure",
        "refrigerant_cycle",
        "energy_counters",
        "controls",
        "settings",
        "compressor_modulation",
    )
    return [
        (name, component)
        for name in names
        if isinstance(component := getattr(device, name, None), Component)
    ]


async def main() -> int:
    """Read one device and print it."""
    # The backend logs a failed connect at ERROR with its traceback; the
    # messages below say it in one line.
    logging.getLogger().addHandler(logging.NullHandler())

    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_connection_args(parser, connections=CONNECTIONS)
    parser.add_argument("--unit", type=int, default=1, help="Modbus unit id")
    parser.add_argument(
        "--meter", action="store_true", help="the unit is an SDM120, not a heat pump"
    )
    parser.add_argument(
        "--december-2023",
        action="store_true",
        help="the heat pump is from December 2023 or later: also read its "
        "energy counters and compressor modulation",
    )
    parser.add_argument(
        "--raw", action="store_true", help="also dump every register read, as JSON"
    )
    args = parser.parse_args()

    try:
        connection = await connect_from_args(args)
    except ModbusError as err:
        # A connect timeout arrives with no message of its own.
        detail = str(err) or type(err).__name__
        print(f"Could not connect to {args.target}: {detail}")
        return 1

    unit = CountingUnit(connection.for_unit(args.unit))
    device: ThermaV | Sdm120 = (
        Sdm120(unit)
        if args.meter
        else ThermaV(unit, from_december_2023=args.december_2023)
    )
    try:
        report = await device.async_update()
        product = (
            await device.async_read_product() if isinstance(device, ThermaV) else False
        )
        reads = unit.reads
        raw = (
            await device.async_read_raw(name for name, _ in served_components(device))
            if args.raw
            else None
        )
    except ModbusError as err:
        print(f"Could not read the device: {str(err) or type(err).__name__}")
        return 1
    finally:
        await connection.close()

    served = served_components(device)
    if product and isinstance(device, ThermaV):
        served.append(("product", device.product))
    for name, component in served:
        print()
        print_component(component, title=name)
    if report.failed:
        print("\nFailed to read:")
        for name, error in report.failed.items():
            print(f"  {name}: {str(error) or type(error).__name__}")
    if raw is not None:
        print("\nRaw registers")
        print(json.dumps(raw, indent=2))
    print(f"\n{reads} Modbus reads")
    return 0


raise SystemExit(asyncio.run(main()))
