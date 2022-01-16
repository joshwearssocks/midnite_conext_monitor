#!/usr/bin/env python3

from pyModbusTCP.client import ModbusClient
import dataclasses
import numpy as np
from modbus_control import ModbusControl, ModbusRegister
from enum import IntEnum

MODBUS_ADDR = 10

class BinaryState(IntEnum):
    Disable = 0
    Enable = 1

class OperatingState(IntEnum):
    Hibernate = 0
    Power_Save = 1
    Safe_Mode = 2
    Operating = 3
    Diagnostic_Mode = 4
    Remote_Power_Off = 5
    Data_Not_Available = 255

class InverterStatus(IntEnum):
    Invert = 1024
    AC_Pass_Through = 1025
    APS_Only = 1026
    Load_Sense = 1027
    Inverter_Disabled = 1028
    Load_Sense_Ready = 1029
    Engaging_Inverter = 1030
    Invert_Fault = 1031
    Inverter_Standby = 1032
    Grid_Tied = 1033
    Grid_Support = 1034
    Gen_Support = 1035
    Sell_To_Grid = 1036
    Load_Shaving = 1037
    Grid_Frequency_Stabilization = 1038

class ChargerStatus(IntEnum):
    Not_Charging = 768
    Bulk = 769
    Absorption = 770
    Overcharge = 771
    Equalize = 772
    Float = 773
    No_Float = 774
    Constant_VI = 775
    Charger_Disabled = 776
    Qualifying_AC = 777
    Qualifying_APS = 778
    Engaging_Charger = 779
    Charge_Fault = 780
    Charger_Suspend = 781
    AC_Good = 782
    APS_Good = 783
    AC_Fault = 784
    Charge = 785
    Absorption_Exit_Pending = 786
    Ground_Fault = 787
    AC_Good_Pending = 788

@dataclasses.dataclass(frozen=True)
class Conext:
    # General information
    device_name: ModbusRegister = ModbusRegister(
        addr=0x0000, reg_type=str, reg_len=8
    )
    device_state: ModbusRegister = ModbusRegister(
        addr=0x0040, reg_type=OperatingState
    )
    inverter_status: ModbusRegister = ModbusRegister(
        addr=0x007A, reg_type=InverterStatus
    )
    charger_status: ModbusRegister = ModbusRegister(
        addr=0x007B, reg_type=ChargerStatus
    )
    # Grid support configuration
    grid_support: ModbusRegister = ModbusRegister(
        addr=0x01B3, reg_type=BinaryState
    )
    grid_support_voltage: ModbusRegister = ModbusRegister(
        addr=0x0178, reg_type=np.uint32, reg_len=2, unit='V', scale=0.001, offset=0.0
    )
    sell: ModbusRegister = ModbusRegister(
        addr=0x0162, reg_type=BinaryState
    )
    maximum_sell_amps: ModbusRegister = ModbusRegister(
        addr=0x01B4, reg_type=np.uint32, reg_len=2, unit='A', scale=0.001, offset=0.0
    )
    grid_tie_sell_level: ModbusRegister = ModbusRegister(
        addr=0x00BF, reg_type=np.uint16
    )
    sell_block_start: ModbusRegister = ModbusRegister(
        addr=0x01F7, reg_type=np.uint16, unit='min'
    )
    sell_block_end: ModbusRegister = ModbusRegister(
        addr=0x01F8, reg_type=np.uint16, unit='min'
    )
    # Battery information
    charger: ModbusRegister = ModbusRegister(
        addr=0x0164, reg_type=BinaryState
    )
    equalize_now: ModbusRegister = ModbusRegister(
        addr=0x0170, reg_type=BinaryState
    )
    recharge_voltage: ModbusRegister = ModbusRegister(
        addr=0x017A, reg_type=np.uint32, reg_len=2, unit='V', scale=0.001, offset=0.0
    )
    # Advanced
    power_save: ModbusRegister = ModbusRegister(
        addr=0x016C, reg_type=BinaryState
    )
    # Power
    invert_dc_power: ModbusRegister = ModbusRegister(
        addr=0x005A, reg_type=np.uint32, reg_len=2, unit='W', scale=1.0, offset=0.0
    )
    grid_output_power: ModbusRegister = ModbusRegister(
        addr=0x0084, reg_type=np.uint32, reg_len=2, unit='W', scale=1.0, offset=0.0
    )
    load_ac_power: ModbusRegister = ModbusRegister(
        addr=0x009A, reg_type=np.int32, reg_len=2, unit='W', scale=1.0, offset=0.0
    )
    # Energy
    energy_from_battery_today: ModbusRegister = ModbusRegister(
        addr=0x00EC, reg_type=np.uint32, reg_len=2, unit='kWh', scale=0.001, offset=0.0
    )
    grid_input_energy_today: ModbusRegister = ModbusRegister(
        addr=0x0104, reg_type=np.uint32, reg_len=2, unit='kWh', scale=0.001, offset=0.0
    )
    grid_output_energy_today: ModbusRegister = ModbusRegister(
        addr=0x011C, reg_type=np.uint32, reg_len=2, unit='kWh', scale=0.001, offset=0.0
    )
    load_output_energy_today: ModbusRegister = ModbusRegister(
        addr=0x0134, reg_type=np.uint32, reg_len=2, unit='kWh', scale=0.001, offset=0.0
    )

        
if __name__ == '__main__':
    conext_gw = ModbusControl(MODBUS_ADDR, '192.168.2.227', 503)
    conext_gw.connect()
    #conext_gw.get_register(Conext.grid_support_voltage)
    #conext_gw.set_register(Conext.maximum_sell_amps, 21.0)
    #conext_gw.set_register(Conext.grid_support, BinaryState.Enable)
    for f in dataclasses.fields(Conext):
        print(f"{f.name : <25}: {conext_gw.get_register(f.default)} {f.default.unit}")