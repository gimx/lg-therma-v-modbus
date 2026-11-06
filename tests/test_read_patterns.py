"""Pins the block reads the heat pump tolerates: few, small and gap-free."""

from __future__ import annotations

from modbus_connection.mock import MockModbusUnit

from lg_therma_v_modbus import ThermaV
from lg_therma_v_modbus.therma_v import WARM_UP_REQUESTS

# The heat pump chokes on large ranges; nothing a poll reads may exceed this.
LARGEST_BLOCK = 17


async def test_a_poll_is_one_read_per_sub_system(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v.async_update()

    blocks = therma_v_unit.read_events[WARM_UP_REQUESTS:]
    assert [(e.register_type, e.address, e.count) for e in blocks] == [
        ("discrete", 0, 17),
        ("input", 0, 13),
        ("input", 13, 1),
        ("input", 16, 9),
        ("coil", 0, 6),
        ("holding", 0, 10),
    ]


async def test_a_newer_product_adds_two_blocks(
    therma_v_2023: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v_2023.async_update()

    blocks = therma_v_unit.read_events[WARM_UP_REQUESTS:]
    assert [(e.register_type, e.address, e.count) for e in blocks] == [
        ("discrete", 0, 17),
        ("input", 0, 13),
        ("input", 13, 1),
        ("input", 16, 9),
        ("input", 36, 10),
        ("coil", 0, 6),
        ("holding", 0, 10),
        ("holding", 23, 1),
    ]


async def test_no_block_reads_a_register_nobody_documented(
    therma_v_2023: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v_2023.async_update()

    undocumented = {14, 15}  # 30015 and 30016, which LG leaves blank
    for event in therma_v_unit.read_events[WARM_UP_REQUESTS:]:
        if event.register_type == "input":
            assert not undocumented & set(
                range(event.address, event.address + event.count)
            )


async def test_no_block_exceeds_what_the_heat_pump_tolerates(
    therma_v_2023: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v_2023.async_update()

    assert max(e.count for e in therma_v_unit.read_events) <= LARGEST_BLOCK
