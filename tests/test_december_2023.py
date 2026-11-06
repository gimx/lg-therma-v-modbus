"""Pins the registers only products from December 2023 on have."""

from __future__ import annotations

import pytest
from modbus_connection import IllegalDataAddressError
from modbus_connection.mock import MockModbusUnit, WriteEvent

from lg_therma_v_modbus import ThermaV
from lg_therma_v_modbus.therma_v import (
    DECEMBER_2023_COMPONENTS,
    validate_compressor_modulation,
)


def test_an_older_product_has_neither_component(therma_v: ThermaV) -> None:
    assert therma_v.energy_counters is None
    assert therma_v.compressor_modulation is None


async def test_an_older_product_never_reads_their_registers(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v.async_update()

    reads = {(e.register_type, e.address) for e in therma_v_unit.read_events}
    assert not {
        address
        for space, address in reads
        if space == "input" and address >= 25 and address < 9000
    }
    assert ("holding", 23) not in reads


async def test_a_newer_product_polls_them(therma_v_2023: ThermaV) -> None:
    report = await therma_v_2023.async_update()

    assert report.complete
    assert set(DECEMBER_2023_COMPONENTS) <= report.updated


async def test_energy_counters_join_their_words(therma_v_2023: ThermaV) -> None:
    await therma_v_2023.async_update_readings()
    counters = therma_v_2023.energy_counters
    assert counters is not None

    assert counters.energy_instantaneous_total == 1500
    assert counters.energy_accumulative_total == 65536
    assert counters.energy_instantaneous_heat == 3200
    assert counters.energy_accumulative_cool == 12
    assert counters.energy_accumulative_dhw == 4096


async def test_energy_counters_are_one_block(
    therma_v_2023: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v_2023.async_update_readings()

    assert ("input", 36, 10) in [
        (e.register_type, e.address, e.count) for e in therma_v_unit.read_events
    ]


async def test_compressor_modulation(therma_v_2023: ThermaV) -> None:
    await therma_v_2023.async_update_settings()

    assert therma_v_2023.compressor_modulation is not None
    assert therma_v_2023.compressor_modulation.compressor_modulation == 60


@pytest.mark.parametrize("value", [0, 40, 75, 100])
async def test_modulation_is_written(
    therma_v_2023: ThermaV, therma_v_unit: MockModbusUnit, value: int
) -> None:
    events: list[WriteEvent] = []
    therma_v_unit.on_write(events.append)
    assert therma_v_2023.compressor_modulation is not None

    await therma_v_2023.compressor_modulation.write("compressor_modulation", value)

    assert [(e.register_type, e.address, e.values) for e in events] == [
        ("holding", 23, [value])
    ]


@pytest.mark.parametrize("value", [1, 39, 101, -1])
async def test_modulation_outside_what_the_register_defines_is_refused(
    therma_v_2023: ThermaV, therma_v_unit: MockModbusUnit, value: int
) -> None:
    events: list[WriteEvent] = []
    therma_v_unit.on_write(events.append)
    assert therma_v_2023.compressor_modulation is not None

    with pytest.raises(ValueError, match="compressor modulation"):
        await therma_v_2023.compressor_modulation.write("compressor_modulation", value)

    assert events == []


def test_the_validator_returns_what_it_accepts() -> None:
    assert validate_compressor_modulation(40.0) == 40


async def test_an_older_product_refusing_them_fails_only_those_blocks(
    therma_v_unit: MockModbusUnit,
) -> None:
    therma_v_unit.fail_read(36, IllegalDataAddressError(), register_type="input")
    therma_v_unit.fail_read(23, IllegalDataAddressError(), register_type="holding")
    heat_pump = ThermaV(therma_v_unit, from_december_2023=True)

    report = await heat_pump.async_update()

    assert set(report.failed) == set(DECEMBER_2023_COMPONENTS)
    assert "readings" in report.updated
