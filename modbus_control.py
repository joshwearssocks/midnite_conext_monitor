#!/usr/bin/env python3

import numpy as np
from typing import Tuple, Union, List
from dataclasses import dataclass
from pyModbusTCP.client import ModbusClient
import logging
import enum

class SizedStr:
    _string: str
    _strlen: int

    def __init__(self, string: str, strlen: int) -> None:
        self._strlen = strlen
        self.string = string

    @property
    def string(self) -> str:
        return self._string

    @string.setter
    def string(self, string: str) -> None:
        if len(string) > self._strlen:
            raise ValueError(f"Expected string of length <= {self._strlen}, got {len(string)}.")
        self._string = string

    def __str__(self) -> str:
        return self.string
    
    def __len__(self) -> str:
        return self._strlen

@dataclass
class ModbusRegister:
    addr: int
    reg_type: Tuple[str, np.int16, np.uint16, np.uint32, np.int32, enum.EnumMeta]
    reg_len: int = 1
    unit: str = 'state'
    scale: float = 1.0
    offset: float = 0.0

class ModbusControl:
    def __init__(self, modbus_addr: int, host: str, port: int = 503):
        self.client = ModbusClient(host=host, port=port, unit_id=modbus_addr, timeout=5)
        self.logger = logging.getLogger(self.__class__.__name__)
        logging.basicConfig(level=logging.INFO)

    def connect(self):
        self.client.open()

    def disconnect(self):
        self.client.close()

    def get_register(self, reg: ModbusRegister) -> Union[str,float]:
        if not self.client.is_open():
            raise ConnectionError("Modbus client not connected.")
        
        ret = self.client.read_holding_registers(reg.addr, reg.reg_len)
        if ret == None:
            raise ValueError("Failed to retrieve modbus register.")

        val: Union[str,float]
        if reg.reg_type == str:
            val = ''
            for two_char in ret:
                val += chr((two_char & 0xFF00) >> 8)
                val += chr(two_char & 0x00FF)
            val = val.rstrip('\x00')
        elif reg.reg_len == 1: # uint16 or enum
            val = reg.reg_type(ret[0])
        elif reg.reg_len == 2: # uint32 or int32
            val = reg.reg_type((ret[0] << 16) + ret[1])
        else:
            raise ValueError("Unable to decode modbus register.")

        if isinstance(reg.reg_type, enum.EnumMeta):
            # Print enum name
            self.logger.debug("Read holding register 0x%04X: %s", reg.addr, val.name)
            val = val.name
        elif reg.reg_type == str:
            # Print string
            self.logger.debug("Read holding register 0x%04X: %s", reg.addr, val)
        else:
            # Apply scaling and offset for numbers
            val = val * reg.scale + reg.offset
            if reg.scale == 1.0:
                val = int(val)
            self.logger.debug("Read holding register 0x%04X: %.2f %s", reg.addr, val, reg.unit)

        return val
        
    def set_register(self, reg: ModbusRegister, val: Union[float, enum.EnumMeta]) -> None:
        if not self.client.is_open():
            raise ConnectionError("Modbus client not connected.")

        if reg.reg_type == str:
            raise ValueError("String writes are not implemented.")

        vals: List[int]
        if isinstance(reg.reg_type, enum.EnumMeta) and isinstance(val, reg.reg_type):
            vals = [val.value]
        else:
            unscaled_val = int((val - reg.offset) / reg.scale)
            if reg.reg_len == 1: # uint16 or enum that was passed as a int
                vals = [unscaled_val]
            elif reg.reg_len == 2: # uint32 or int32
                vals = [
                    unscaled_val >> 16,
                    unscaled_val & 0xFFFF
                ]
        
        ret = self.client.write_multiple_registers(reg.addr, vals)
        if ret == None:
            raise ValueError("Failed to write modbus registers.")

        if round(self.get_register(reg), 2) != round(val, 2):
            raise ValueError("Register contents do not match expected value after writing.")

        self.logger.debug("Set holding register 0x%04X to %.2f %s", reg.addr, val, reg.unit)
