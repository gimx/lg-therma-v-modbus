"""Pins the SDM120 register map."""

from __future__ import annotations

from modbus_connection.mock import MockModbusUnit

from lg_therma_v_modbus import Sdm120


async def test_readings(sdm120: Sdm120) -> None:
    report = await sdm120.async_update()

    assert report.complete
    assert sdm120.readings.voltage == 231.5
    assert sdm120.readings.active_power == 1250.0
    assert sdm120.readings.total_energy == 4321.75


async def test_each_value_is_its_own_request(
    sdm120: Sdm120, sdm120_unit: MockModbusUnit
) -> None:
    await sdm120.async_update()

    assert [(e.register_type, e.address, e.count) for e in sdm120_unit.read_events] == [
        ("input", 0, 2),
        ("input", 12, 2),
        ("input", 342, 2),
    ]
