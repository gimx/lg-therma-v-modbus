"""Pins the Therma V register map: addresses, scaling and polling."""

from __future__ import annotations

import pytest
from modbus_connection import ModbusConnectionError, ModbusTimeoutError
from modbus_connection.mock import MockModbusUnit, WriteEvent

from lg_therma_v_modbus import (
    ControlMethod,
    EnergyState,
    OperationCycle,
    OperationMode,
    ProductType,
    ThermaV,
)
from lg_therma_v_modbus.therma_v import WARM_UP_REQUESTS

BEFORE_2023 = {
    "status",
    "readings",
    "water_pressure",
    "refrigerant_cycle",
    "controls",
    "settings",
}


async def test_update_reads_every_sub_system(therma_v: ThermaV) -> None:
    report = await therma_v.async_update()

    assert report.complete
    assert report.updated == BEFORE_2023


async def test_status_bits(therma_v: ThermaV) -> None:
    await therma_v.async_update_readings()

    assert therma_v.status.compressor is True
    assert therma_v.status.defrosting is False
    assert therma_v.status.backup_heater_step_1 is True
    assert therma_v.status.backup_heater_step_2 is False
    assert therma_v.status.mix_pump is True
    assert therma_v.status.water_flow_too_low is False


async def test_readings_are_scaled_and_signed(therma_v: ThermaV) -> None:
    await therma_v.async_update_readings()
    readings = therma_v.readings

    assert readings.operation_cycle is OperationCycle.HEATING
    assert readings.water_inlet_temperature == 30.1
    assert readings.water_outlet_temperature == 35.2
    assert readings.dhw_tank_temperature == 47.8
    assert readings.circuit_1_room_air_temperature == 21.5
    assert readings.flow_rate == 12.3
    assert readings.circuit_2_flow_temperature == 33.1
    assert readings.circuit_2_room_air_temperature == 18.7
    assert readings.energy_state is EnergyState.NORMAL_OPERATION
    assert readings.outside_air_temperature == -3.5


async def test_water_pressure(therma_v: ThermaV) -> None:
    await therma_v.async_update_readings()

    assert therma_v.water_pressure.water_pressure == 1.8


async def test_refrigerant_cycle(therma_v: ThermaV) -> None:
    await therma_v.async_update_readings()
    cycle = therma_v.refrigerant_cycle

    assert cycle.pipe_in_temperature == 30.1
    assert cycle.pipe_out_temperature == 25.2
    assert cycle.suction_temperature == 4.1
    assert cycle.discharge_temperature == 61.2
    assert cycle.heat_exchanger_temperature == 9.0
    assert cycle.evaporator_outlet_temperature == 8.5
    assert cycle.high_pressure == 24.5
    assert cycle.low_pressure == 8.1
    assert cycle.compressor_frequency == 63


async def test_controls_and_settings(therma_v: ThermaV) -> None:
    await therma_v.async_update_settings()

    assert therma_v.controls.heating_cooling_enabled is True
    assert therma_v.controls.silent_mode is False
    settings = therma_v.settings
    assert settings.operation_mode is OperationMode.HEAT
    assert settings.control_method is ControlMethod.WATER_OUTLET_TEMPERATURE
    assert settings.circuit_1_target_temperature == 40.0
    assert settings.circuit_1_room_air_temperature == 21.0
    assert settings.circuit_2_target_temperature == 35.0
    assert settings.circuit_2_room_air_temperature == 18.0
    assert settings.dhw_target_temperature == 48.0
    assert settings.circuit_1_auto_mode_shift == 2
    assert settings.circuit_2_auto_mode_shift == 1
    assert settings.energy_state_input is EnergyState.NORMAL_OPERATION


async def test_product_is_read_on_request(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    assert await therma_v.async_read_product() is True

    assert therma_v.product.product_group == 0x83
    assert therma_v.product.product_type is ProductType.MONOBLOC
    assert [
        (e.address, e.count) for e in therma_v_unit.read_events[WARM_UP_REQUESTS:]
    ] == [
        (9997, 1),
        (9998, 1),
    ]


async def test_product_is_not_part_of_a_poll(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v.async_update()

    assert 9997 not in {e.address for e in therma_v_unit.read_events}


async def test_a_product_that_does_not_answer_is_unknown(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    therma_v_unit.fail_read(9997, ModbusTimeoutError(), register_type="input")

    assert await therma_v.async_read_product() is False
    assert therma_v.product.product_type is None


async def test_product_read_on_a_dead_link_raises(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    therma_v_unit.fail_requests(ModbusConnectionError())

    with pytest.raises(ModbusConnectionError):
        await therma_v.async_read_product()


async def test_writing_a_coil(therma_v: ThermaV, therma_v_unit: MockModbusUnit) -> None:
    events: list[WriteEvent] = []
    therma_v_unit.on_write(events.append)

    await therma_v.controls.write("silent_mode", True)
    await therma_v.controls.write("trigger_dhw_disinfection", True)

    assert [(e.register_type, e.address, e.values) for e in events] == [
        ("coil", 2, [True]),
        ("coil", 3, [True]),
    ]


async def test_writing_settings(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    events: list[WriteEvent] = []
    therma_v_unit.on_write(events.append)

    await therma_v.settings.write("dhw_target_temperature", 50.5)
    await therma_v.settings.write("operation_mode", OperationMode.AUTO)
    await therma_v.settings.write("control_method", ControlMethod.ROOM_AIR)
    await therma_v.settings.write("energy_state_input", EnergyState.POWER_SAVING)
    await therma_v.settings.write("circuit_1_room_air_temperature", 20.5)

    assert [(e.register_type, e.address, e.values) for e in events] == [
        ("holding", 8, [505]),
        ("holding", 0, [3]),
        ("holding", 1, [2]),
        ("holding", 9, [7]),
        ("holding", 3, [205]),
    ]


async def test_readings_are_read_only(therma_v: ThermaV) -> None:
    with pytest.raises(AttributeError):
        await therma_v.readings.write("water_inlet_temperature", 20.0)


async def test_an_unknown_code_reads_as_none(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    therma_v_unit.input[1] = 9

    await therma_v.async_update_readings()

    assert therma_v.readings.operation_cycle is None


async def test_first_poll_warms_the_link_up_on_an_input_register(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v.async_update_readings()

    warm_up = therma_v_unit.read_events[:WARM_UP_REQUESTS]
    assert [(e.register_type, e.address, e.count) for e in warm_up] == [
        ("input", 0, 1)
    ] * WARM_UP_REQUESTS


async def test_warm_up_runs_once(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    await therma_v.async_update_readings()
    reads = len(therma_v_unit.read_events)
    await therma_v.async_update_readings()

    second = therma_v_unit.read_events[reads:]
    assert ("input", 0, 1) not in [
        (e.register_type, e.address, e.count) for e in second
    ]


async def test_unanswered_warm_up_requests_are_not_an_error(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    answers = iter([ModbusTimeoutError(), ModbusTimeoutError()])
    read = therma_v_unit.read_input_registers

    async def read_input_registers(address: int, count: int) -> list[int]:
        if address == 0 and count == 1 and (error := next(answers, None)):
            raise error
        return await read(address, count)

    therma_v_unit.read_input_registers = read_input_registers  # type: ignore[method-assign]

    report = await therma_v.async_update_readings()

    assert report.complete


async def test_dead_link_raises(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    therma_v_unit.fail_requests(ModbusConnectionError())

    with pytest.raises(ModbusConnectionError):
        await therma_v.async_update()


async def test_one_failing_block_keeps_the_rest(
    therma_v: ThermaV, therma_v_unit: MockModbusUnit
) -> None:
    therma_v_unit.fail_read(0, ModbusTimeoutError(), register_type="coil")

    report = await therma_v.async_update()

    assert set(report.failed) == {"controls"}
    assert report.updated == BEFORE_2023 - {"controls"}
