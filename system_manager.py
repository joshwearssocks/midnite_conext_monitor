#!/usr/bin/env python3

from modbus_control import ModbusControl
from conext_regmap import Conext, BinaryState
from midnite_classic_regmap import MidniteClassic

from influxdb import InfluxDBClient

import dataclasses
from enum import Enum, auto
from typing import Any, Callable, Optional, Union, Dict, List
import signal
import time
from datetime import datetime
import logging

DATA_FIELDS = Dict[str,Union[str,int,float]]
INFLUX_DICT = Dict[str,Union[str,DATA_FIELDS]]

@dataclasses.dataclass
class DeviceInfo:
    name: str
    control: ModbusControl
    regmap: Union[Conext, MidniteClassic]

class SystemManager:
    """Configures and logs data from the inverter and charge controller."""

    callbacks: List[Callable[[Dict[str,DATA_FIELDS]], Any]] = []

    def __init__(self, devices: List[DeviceInfo], influx_client: Optional[InfluxDBClient]):
        self.devices = devices
        self.influx_client = influx_client
        self.data_dict: Dict[str, Optional[DATA_FIELDS]] = {
            device.name: None for device in devices
        }
        self.logger = logging.getLogger(self.__class__.__name__)

    def add_callback(self, func: Callable[[Dict[str,DATA_FIELDS]], Any]):
        """Adds a function to be called at the end of each data collection period.
        
        The callback function must accept a dictionary of field:value dictionaries.
        """
        self.callbacks.append(func)

    def _process_data(self, signum, _) -> None:
        """Reads all registers from the inverter and charge controller."""

        self.logger.debug("Processing...")
        json_body = []
        # Read holding registers from all devices
        for device in self.devices:
            # Reset the value map
            self.data_dict[device.name] = None
            try:
                device.control.connect()
                self.data_dict[device.name] = {
                    f.name:  device.control.get_register(f.default) for f in dataclasses.fields(device.regmap)
                }
                json_body.append({
                    "measurement": device.name,
                    "tags": {
                        "modbus_id": device.control.client.unit_id()
                    },
                    "fields": self.data_dict[device.name]
                })
            # Never fail
            except (ValueError, ConnectionError) as e:
                self.logger.error(f"Unable to process data from {device.name}: {e}")
            finally:
                device.control.disconnect()
        # Transmit data to influxdb
        if len(json_body) > 0:
            if self.influx_client:
                self.logger.debug("Sending points to influxdb...")
                self.influx_client.write_points(json_body)
            
        # Do some logic
        for func in self.callbacks:
            func(self.data_dict)

    def start(self, period_s: int = 10) -> None:
        """Starts a timer for the monitor routine."""

        signal.signal(signal.SIGALRM, self._process_data)
        timer_start_delay = period_s - (datetime.now().second % period_s)
        signal.setitimer(signal.ITIMER_REAL, timer_start_delay, period_s)
