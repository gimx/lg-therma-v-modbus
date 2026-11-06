# lg-therma-v-modbus

Read and control LG Therma V heat pumps over Modbus, as typed Python objects
rather than register numbers. The Eastron SDM120 energy meter that is often
wired onto the same RS-485 line is included.

The library maps the registers onto
[modbus-connection](https://github.com/home-assistant-libs/modbus-connection)'s device model:
you hand it a `ModbusUnit`, call `async_update()`, and read sub-systems as
attributes. It owns no connection and no I/O policy — the caller does.

## Supported devices

**`ThermaV` — the heat pump.** Every register LG's Modbus register list
documents: 17 discrete inputs, 6 coils, input registers 30001 to 30025 and 30037
to 30046, holding registers 40001 to 40010 and 40024, and the two product
registers 39998 and 39999. They are split into sub-systems that are read
separately, so a block a product refuses cannot take the others with it.

| Sub-system | Space | Content |
| :--- | :--- | :--- |
| `status` | discrete inputs | compressor, defrosting, pumps, heaters, error and availability bits |
| `readings` | input registers | water, room air, DHW tank, solar collector and outside air temperatures, flow rate, error code, operation cycle, energy state |
| `water_pressure` | input register | the water circuit's pressure |
| `refrigerant_cycle` | input registers | refrigerant temperatures and pressures, compressor frequency |
| `controls` | coils (writable) | heating/cooling and DHW on/off, silent mode, emergency stop, and the triggers for DHW disinfection and emergency operation |
| `settings` | holding registers (writable) | operation mode, control method, target temperatures of both circuits and of the DHW tank, room air inputs, auto-mode shifts, energy state input |
| `product` | input registers | product group and type, read once with `async_read_product()` |
| `energy_counters` | input registers | the heat pump's own energy measurement, **December 2023 or later** |
| `compressor_modulation` | holding register (writable) | limit on the compressor, **December 2023 or later** |

Two heating circuits exist. Each has a target temperature, a room air
temperature and an auto-mode shift. The operation mode and the control method
(which sensor the target is held against) apply to both.

### Products from December 2023

Products from before December 2023 do not have the energy counters (input
registers 30037 to 30046) and the compressor modulation (holding register
40024), and refuse a read of them. They are therefore left alone unless you say
the product is newer:

```python
heat_pump = ThermaV(unit, from_december_2023=True)
```

Without it `energy_counters` and `compressor_modulation` are `None`, and a poll
never asks for their registers. With it they are polled like the rest; a
product that turns out not to have them lists them in the report's `failed`.

The compressor modulation is 0 (not used) or 40 to 100. Any other value
raises `ValueError` before anything is written.

**`Sdm120` — the meter.** An Eastron SDM120 single-phase energy meter, read
over its input registers as IEEE-754 floats: `voltage` (V), `active_power` (W)
and `total_energy` (kWh). It is a different unit on the same line, so it takes
its own `ModbusUnit`.

## Usage

```python
import asyncio

from modbus_connection import ModbusSerialParams
from modbus_connection.tmodbus import ModbusConnection
from lg_therma_v_modbus import OperationMode, Sdm120, ThermaV


async def main() -> None:
    connection = ModbusConnection(ModbusSerialParams(device="/dev/ttyUSB0"))
    try:
        heat_pump = ThermaV(connection.for_unit(1))
        meter = Sdm120(connection.for_unit(2))

        await heat_pump.async_update()
        await meter.async_update()

        print("Outside:", heat_pump.readings.outside_air_temperature, "°C")
        print("Flow:", heat_pump.readings.flow_rate, "l/min")
        print("Compressor running:", heat_pump.status.compressor)
        print("Mode:", heat_pump.settings.operation_mode)
        print("Pressure:", heat_pump.water_pressure.water_pressure, "bar")
        print("Power:", meter.readings.active_power, "W")

        await heat_pump.settings.write("dhw_target_temperature", 48.0)
        await heat_pump.settings.write("operation_mode", OperationMode.AUTO)
        await heat_pump.controls.write("silent_mode", True)
    finally:
        await connection.close()


asyncio.run(main())
```

A poll reads each sub-system independently: one slow or refused block does not
take the rest of the poll with it. Every update method returns an
`UpdateReport` — a failed component keeps its previous values, does not notify
its listeners, and is listed by attribute name with its error, while every
other component refreshes and notifies once the whole poll is done. A dead
link (`ModbusConnectionError`) raises, and so does a timeout before any
component has answered.

```python
report = await heat_pump.async_update()
for name, error in report.failed.items():
    print(f"{name} kept its previous values: {error}")
```

`ThermaV` splits its poll by what it reads:

- `async_update_readings()` — what the heat pump reports: `status`, `readings`,
  `water_pressure`, `refrigerant_cycle` and, if enabled, `energy_counters`.
- `async_update_settings()` — what it has been told: `controls`, `settings` and,
  if enabled, `compressor_modulation`.
  Run one after a write to read back what took effect.
- `async_update()` — both, in one merged report.

Writing is by field name through the component: `await heat_pump.controls.write(
"silent_mode", True)`. Only the fields of `controls`, `settings` and
`compressor_modulation` are writable; writing a reading raises `AttributeError`.

`trigger_dhw_disinfection` and `trigger_emergency_operation` are one-shot
triggers: write `True` to start the operation. The heat pump keeps its status
when they are cleared, so they are not states to read back; `status` reports
what is running (`dhw_tank_disinfection`, `emergency_operation_available_*`).

## How the Therma V wants to be talked to

The heat pump is picky about its Modbus master. Four things matter.

- **It answers from the third request.** On a fresh link its first requests
  go unanswered, and they must be aimed at an input register or a coil. The
  first poll of a `ThermaV` therefore starts with three reads of input
  register 0. An unanswered one is expected and does not fail the poll; a dead
  link still does. This happens once per object, so build a new `ThermaV`
  after a reconnect that should warm up again.
- **Never stop polling.** After five minutes without a request the heat pump
  shows the error `CH 03`, and only cutting its power clears it. A caller that
  starts polling has to keep going. A bridge that polls on its own behalf
  keeps the heat pump out of that state when the caller is down.
- **Poll at a moderate pace.** Neither very fast nor very slow polling stays
  error-free for long. A request spacing of about 100 ms suits a USB adapter
  and about 30 ms a network bridge; set it on the unit with
  `unit.set_message_spacing()`.
- **Do not read large ranges.** The library reads each sub-system as a single
  small block (at most 17 addresses), which is what the heat pump tolerates.
  It never reads across the registers LG leaves blank (30015, 30016).

The unit ID is the one set on the heat pump's control panel under
*Connectivity > Modbus address*.

## Naming the link

How to name the link depends on what sits between you and the RS-485 line,
not on the heat pump:

| Between you and the line | Parameters |
| :--- | :--- |
| Nothing: a USB or serial adapter | `ModbusSerialParams(device="/dev/ttyUSB0")` |
| A box forwarding the RTU frames | `ModbusSerialParams(device="socket://host:port")` |
| A gateway answering Modbus TCP | `ModbusTcpParams(host=...)` |

The heat pump speaks 9600 baud, 8 data bits, no parity and one stop bit, which
are the defaults of `ModbusSerialParams`. ASCII framing is unsupported.

## Register reference

Register numbers are LG's; the Modbus address is the number without its leading
digit, minus one (30003 is input address 2). LG's installation manual labels
the input and holding registers the wrong way round; the tables below are the
corrected ones, and what the heat pump answers.

**Coils** (writable)

| Register | Attribute | LG's name |
| :--- | :--- | :--- |
| 00001 | `heating_cooling_enabled` | Enable/Disable (Heating/Cooling) |
| 00002 | `dhw_enabled` | Enable/Disable (DHW) |
| 00003 | `silent_mode` | Silent Mode Set |
| 00004 | `trigger_dhw_disinfection` | Trigger Disinfection operation |
| 00005 | `emergency_stop` | Emergency Stop |
| 00006 | `trigger_emergency_operation` | Trigger Emergency Operation |

**Discrete inputs** (`status`)

| Register | Attribute | LG's name |
| :--- | :--- | :--- |
| 10001 | `water_flow_too_low` | Water flow status (0 flow rate ok, 1 too low) |
| 10002 | `water_pump` | Water Pump status |
| 10003 | `external_water_pump` | Ext. Water Pump status |
| 10004 | `compressor` | Compressor status |
| 10005 | `defrosting` | Defrosting status |
| 10006 | `dhw_heating` | DHW heating status (DHW Thermal On/Off) |
| 10007 | `dhw_tank_disinfection` | DHW Tank disinfection status |
| 10008 | `silent_mode` | Silent mode status |
| 10009 | `cooling` | Cooling status |
| 10010 | `solar_pump` | Solar pump status |
| 10011 | `backup_heater_step_1` | Backup heater (Step 1) status |
| 10012 | `backup_heater_step_2` | Backup heater (Step 2) status |
| 10013 | `dhw_boost_heater` | DHW boost heater status |
| 10014 | `error` | Error status |
| 10015 | `emergency_operation_available_space` | Emergency Operation Available (Space heating/cooling) |
| 10016 | `emergency_operation_available_dhw` | Emergency Operation Available (DHW) |
| 10017 | `mix_pump` | Mix pump status |

**Input registers**

| Register | Attribute | LG's name | Scale |
| :--- | :--- | :--- | :--- |
| 30001 | `readings.error_code` | Error Code | |
| 30002 | `readings.operation_cycle` | ODU operation Cycle (0 standby, 1 cooling, 2 heating) | |
| 30003 | `readings.water_inlet_temperature` | Water inlet temp. | 0.1 °C |
| 30004 | `readings.water_outlet_temperature` | Water outlet temp. | 0.1 °C |
| 30005 | `readings.backup_heater_outlet_temperature` | Backup heater outlet temp. | 0.1 °C |
| 30006 | `readings.dhw_tank_temperature` | DHW tank water temp. | 0.1 °C |
| 30007 | `readings.solar_collector_temperature` | Solar collector temp. | 0.1 °C |
| 30008 | `readings.circuit_1_room_air_temperature` | Room air temp. (Circuit 1) | 0.1 °C |
| 30009 | `readings.flow_rate` | Current Flow rate | 0.1 l/min |
| 30010 | `readings.circuit_2_flow_temperature` | Flow temp. (Circuit 2) | 0.1 °C |
| 30011 | `readings.circuit_2_room_air_temperature` | Room air temp. (Circuit 2) | 0.1 °C |
| 30012 | `readings.energy_state` | Energy State input | |
| 30013 | `readings.outside_air_temperature` | Outdoor Air temp. | 0.1 °C |
| 30014 | `water_pressure.water_pressure` | Water pressure | 0.1 bar |
| 30017 | `refrigerant_cycle.pipe_in_temperature` | Pipe in temp | 0.1 °C |
| 30018 | `refrigerant_cycle.pipe_out_temperature` | Pipe out temp | 0.1 °C |
| 30019 | `refrigerant_cycle.suction_temperature` | Suction temp | 0.1 °C |
| 30020 | `refrigerant_cycle.discharge_temperature` | INV1 dis. temp | 0.1 °C |
| 30021 | `refrigerant_cycle.heat_exchanger_temperature` | HEX temp | 0.1 °C |
| 30022 | `refrigerant_cycle.evaporator_outlet_temperature` | (not named by LG) | 0.1 °C |
| 30023 | `refrigerant_cycle.high_pressure` | HighPress | 0.01 bar |
| 30024 | `refrigerant_cycle.low_pressure` | LowPress | 0.01 bar |
| 30025 | `refrigerant_cycle.compressor_frequency` | Inverter [Hz] | Hz |
| 30037–30038 | `energy_counters.energy_instantaneous_total` | ENERGY_INSTANTANEOUS_TOTAL | Wh |
| 30039–30040 | `energy_counters.energy_accumulative_total` | ENERGY_ACCUMULATIVE_TOTAL | Wh |
| 30041–30042 | `energy_counters.energy_instantaneous_heat` | ENERGY_INSTANTANEOUS_HEAT | Wh |
| 30043–30044 | `energy_counters.energy_accumulative_cool` | ENERGY_ACCUMULATIVE_COOL | Wh |
| 30045–30046 | `energy_counters.energy_accumulative_dhw` | ENERGY_ACCUMULATIVE_DHW | Wh |
| 39998 | `product.product_group` | Product Group (0x80, 0x83, 0x88, 0x89) | |
| 39999 | `product.product_type` | Product Info (0 split, 3 monobloc, 4 high temp., 5 medium temp., 6 system boiler) | |

The registers from 30037 on are from December 2023 or later, except 39998 and
39999.

**Holding registers** (writable)

| Register | Attribute | LG's name |
| :--- | :--- | :--- |
| 40001 | `settings.operation_mode` | Operation Mode (0 cooling, 3 auto, 4 heating) |
| 40002 | `settings.control_method` | Control method (Circuit 1/2): 0 water outlet, 1 water inlet, 2 room air |
| 40003 | `settings.circuit_1_target_temperature` | Target temp (Heating/Cooling) Circuit 1, 0.1 °C |
| 40004 | `settings.circuit_1_room_air_temperature` | Room Air Temp. Circuit 1, 0.1 °C |
| 40005 | `settings.circuit_1_auto_mode_shift` | Shift value (Target) in auto mode Circuit 1, K |
| 40006 | `settings.circuit_2_target_temperature` | Target temp (Heating/Cooling) Circuit 2, 0.1 °C |
| 40007 | `settings.circuit_2_room_air_temperature` | Room Air Temp. Circuit 2, 0.1 °C |
| 40008 | `settings.circuit_2_auto_mode_shift` | Shift value (Target) in auto mode Circuit 2, K |
| 40009 | `settings.dhw_target_temperature` | DHW Target temp., 0.1 °C |
| 40010 | `settings.energy_state_input` | Energy state input (0 to 8) |
| 40024 | `compressor_modulation.compressor_modulation` | Compressor Modulation (0 not used, 40 to 100), December 2023 or later |

The energy states are 0 not used, 1 forced off, 2 normal operation, 3 on
recommendation, 4 on command, 5 on command step 2, 6 on recommendation step 1,
7 power saving and 8 super power saving. 1 to 4 are the SG Ready states of the
terminal block contacts TB_SG1 and TB_SG2.

### Where the sources disagree

The names are LG's own English register list. Where the community
documentation differs, this is what was decided:

- **Pressures.** LG gives 30023 and 30024 in mBar. On a 9 kW monobloc those
  values only make sense at 0.01 bar per step, so that is the scale. Check it
  against your own heat pump.
- **30022.** LG leaves it unnamed. The community documentation calls it the
  vapor temperature after the evaporator, which is where the name comes from.
- **30018.** The community table omits it; LG lists it as "Pipe out temp".
- **Product registers.** The community table lists the product information as
  holding register 49999. LG lists 39998 and 39999 under the input registers, as
  does a working configuration, so those are the ones read.
- **Energy counters.** The names are LG's constants, which call two of the
  values "instantaneous" yet give all of them in Wh. Treat the instantaneous
  ones with care.
- **Not modelled.** Input register 30036, which another project reads as the
  internal power, is in no register list found. Registers 40025 and coil 00007,
  a power limit, appear in one configuration only and not in any register list.

## Checking a real device

`script/query.py` reads one device once and prints every value it serves,
which is the quickest way to see whether it is reachable and addressed
correctly:

```bash
# a USB or serial adapter, heat pump on unit 1
uv run script/query.py /dev/ttyUSB0 --transport serial --unit 1
# the meter on the same line
uv run script/query.py /dev/ttyUSB0 --transport serial --unit 2 --meter
# a box forwarding RTU frames over TCP
uv run script/query.py socket://192.168.1.50:8899 --transport serial --unit 1
# a gateway answering Modbus TCP
uv run script/query.py 192.168.1.60 --port 502 --unit 1
```

It prints the number of Modbus reads and how long they took. `--raw` adds every
register read, undecoded, which is what an issue about a wrong value should
quote.

## Development

```bash
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

The tests run against `modbus-connection`'s in-memory mock, so no hardware is
needed. See [RELEASING.md](RELEASING.md) for publishing a version.
