#!/usr/bin/env python3

from pyModbusTCP.client import ModbusClient
import dataclasses
import numpy as np
from modbus_control import ModbusControl, ModbusRegister
from enum import IntEnum

MODBUS_ADDR = 1

class ComboChargeStage(IntEnum):
    Resting = 0
    Absorb = 3
    BulkMppt = 4
    Float = 5
    FloatMppt = 6
    Equalize = 7
    HyperVoc = 8
    EqMppt = 18

    @classmethod
    def _missing_(cls, value):
        # Only support charge states stored in the upper byte
        return cls(value >> 8)

@dataclasses.dataclass(frozen=True)
class MidniteClassic:
    # Battery
    battery_soc: ModbusRegister = ModbusRegister(
        addr=4372, reg_type=np.uint16, unit='%'
    )
    battery_ah_remaining: ModbusRegister = ModbusRegister(
        addr=4376, reg_type=np.uint16, unit='AH'
    )
    combo_charge_stage: ModbusRegister = ModbusRegister(
        addr=4119, reg_type=ComboChargeStage
    )
    # Temperatures
    t_batt: ModbusRegister = ModbusRegister(
        addr=4131, reg_type=np.uint16, scale=0.1, unit='C'
    )
    t_fet: ModbusRegister = ModbusRegister(
        addr=4132, reg_type=np.uint16, scale=0.1, unit='C'
    )
    # Power
    v_batt: ModbusRegister = ModbusRegister(
        addr=4114, reg_type=np.uint16, scale=0.1, unit='V'
    )
    i_batt: ModbusRegister = ModbusRegister(
        addr=4116, reg_type=np.uint16, scale=0.1, unit='A'
    )
    v_pv: ModbusRegister = ModbusRegister(
        addr=4115, reg_type=np.uint16, scale=0.1, unit='V'
    )
    i_pv: ModbusRegister = ModbusRegister(
        addr=4120, reg_type=np.uint16, scale=0.1, unit='A'
    )
    watts: ModbusRegister = ModbusRegister(
        addr=4118, reg_type=np.uint16, scale=1.0, unit='W'
    )
    # Energy
    kwh_today: ModbusRegister = ModbusRegister(
        addr=4117, reg_type=np.uint16, scale=0.1, unit='kWh'
    )
    kwh_lifetime: ModbusRegister = ModbusRegister(
        addr=4125, reg_type=np.uint32, scale=0.1, unit='kWh'
    )

        
if __name__ == '__main__':
    classic = ModbusControl(MODBUS_ADDR, '192.168.1.10', 502)
    classic.connect()
    for f in dataclasses.fields(MidniteClassic):
        print(f"{f.name : <25}: {classic.get_register(f.default)} {f.default.unit}")