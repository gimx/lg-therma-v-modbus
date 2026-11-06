"""Fixtures: an LG Therma V and an SDM120 on modbus-connection's in-memory mock."""

from __future__ import annotations

import struct

import pytest
from modbus_connection.mock import MockModbusConnection, MockModbusUnit

from lg_therma_v_modbus import Sdm120, ThermaV

THERMA_V_UNIT_ID = 1
SDM120_UNIT_ID = 2


def float_words(value: float) -> list[int]:
    """A float32 as two registers, most significant word first."""
    raw = struct.unpack(">I", struct.pack(">f", value))[0]
    return [raw >> 16, raw & 0xFFFF]


@pytest.fixture
def therma_v_unit(mock_modbus_connection: MockModbusConnection) -> MockModbusUnit:
    """The heat pump's unit, loaded with a plausible winter morning."""
    unit = mock_modbus_connection.for_unit(THERMA_V_UNIT_ID)
    unit.discrete.update({3: True, 4: False, 5: False, 10: True, 11: False, 16: True})
    unit.coil.update({0: True, 1: True, 2: False, 3: False, 4: False, 5: False})
    unit.input.update(
        {
            0: 0,
            1: 2,  # heating
            2: 301,
            3: 352,
            5: 478,
            7: 215,
            8: 123,
            9: 331,
            10: 187,
            11: 2,
            12: (-35) & 0xFFFF,  # signed: 0xFFDD on the wire
            13: 18,  # water pressure
            16: 301,
            17: 252,
            18: 41,
            19: 612,
            20: 90,
            21: 85,
            22: 2450,  # high pressure
            23: 810,  # low pressure
            24: 63,  # compressor frequency
            36: [0, 1500],  # instantaneous total
            38: [0x0001, 0x0000],  # accumulative total: 65536 Wh
            40: [0, 3200],
            42: [0, 12],
            44: [0, 4096],
            9997: 0x83,
            9998: 3,  # monobloc
        }
    )
    unit.holding.update(
        {
            0: 4,
            1: 0,
            2: 400,
            3: 210,
            4: 2,
            5: 350,
            6: 180,
            7: 1,
            8: 480,
            9: 2,
            23: 60,
        }
    )
    return unit


@pytest.fixture
def sdm120_unit(mock_modbus_connection: MockModbusConnection) -> MockModbusUnit:
    """The meter's unit, loaded with a running heat pump's figures."""
    unit = mock_modbus_connection.for_unit(SDM120_UNIT_ID)
    unit.input[0] = float_words(231.5)
    unit.input[12] = float_words(1250.0)
    unit.input[342] = float_words(4321.75)
    return unit


@pytest.fixture
def therma_v(therma_v_unit: MockModbusUnit) -> ThermaV:
    """A heat pump over the loaded unit, from before December 2023."""
    return ThermaV(therma_v_unit)


@pytest.fixture
def therma_v_2023(therma_v_unit: MockModbusUnit) -> ThermaV:
    """A heat pump over the loaded unit, from December 2023 or later."""
    return ThermaV(therma_v_unit, from_december_2023=True)


@pytest.fixture
def sdm120(sdm120_unit: MockModbusUnit) -> Sdm120:
    """A meter over the loaded unit."""
    return Sdm120(sdm120_unit)
