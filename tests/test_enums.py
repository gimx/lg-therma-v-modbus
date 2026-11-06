"""Pins the codes the Therma V uses for its modes."""

from __future__ import annotations

from lg_therma_v_modbus import (
    ControlMethod,
    EnergyState,
    OperationCycle,
    OperationMode,
    ProductType,
)


def test_operation_mode_codes() -> None:
    assert {m.name: m.value for m in OperationMode} == {"COOL": 0, "AUTO": 3, "HEAT": 4}


def test_operation_cycle_codes() -> None:
    assert [s.value for s in OperationCycle] == [0, 1, 2]


def test_control_method_codes() -> None:
    assert [s.value for s in ControlMethod] == [0, 1, 2]


def test_energy_states_are_the_nine_the_register_defines() -> None:
    assert [s.value for s in EnergyState] == list(range(9))


def test_product_type_codes() -> None:
    assert {p.name: p.value for p in ProductType} == {
        "SPLIT": 0,
        "MONOBLOC": 3,
        "HIGH_TEMPERATURE": 4,
        "MEDIUM_TEMPERATURE": 5,
        "SYSTEM_BOILER": 6,
    }
