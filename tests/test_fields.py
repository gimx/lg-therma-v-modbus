"""Guards the register map against two fields claiming one address."""

from __future__ import annotations

from modbus_connection.model import Component

from lg_therma_v_modbus.meter import Sdm120Readings
from lg_therma_v_modbus.therma_v import (
    CompressorModulation,
    Controls,
    EnergyCounters,
    Product,
    Readings,
    RefrigerantCycle,
    Settings,
    Status,
    WaterPressure,
)


def _addresses(component: type[Component]) -> list[int]:
    return [
        field.address + offset
        for field in component.declared_fields.values()
        for offset in range(field.count)
    ]


def test_no_address_is_claimed_twice() -> None:
    for component in (
        Status,
        Controls,
        Readings,
        WaterPressure,
        RefrigerantCycle,
        Product,
        Settings,
        EnergyCounters,
        CompressorModulation,
        Sdm120Readings,
    ):
        addresses = _addresses(component)
        assert len(addresses) == len(set(addresses)), component.__name__


def test_the_therma_v_map_matches_the_register_list() -> None:
    assert sorted(_addresses(Status)) == list(range(17))  # 10001-10017
    assert sorted(_addresses(Controls)) == list(range(6))  # 00001-00006
    assert sorted(_addresses(Readings)) == list(range(13))  # 30001-30013
    assert _addresses(WaterPressure) == [13]  # 30014
    assert sorted(_addresses(RefrigerantCycle)) == list(range(16, 25))  # 30017-30025
    assert sorted(_addresses(Product)) == [9997, 9998]  # 39998, 39999
    assert sorted(_addresses(Settings)) == list(range(10))  # 40001-40010
    assert sorted(_addresses(EnergyCounters)) == list(range(36, 46))  # 30037-30046
    assert _addresses(CompressorModulation) == [23]  # 40024
