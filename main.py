#!/usr/bin/env python3

from modbus_control import ModbusControl
from conext_regmap import Conext, BinaryState
from midnite_classic_regmap import MidniteClassic

from influxdb import InfluxDBClient

import dataclasses
import signal
import time
from typing import Dict, Union
from datetime import datetime
from enum import Enum, auto

MIDNITE_CLASSIC_MODBUS_ADDR = 1
MIDNITE_CLASSIC_IP = '192.168.1.10'
MIDNITE_CLASSIC_PORT = 502
MIDNITE_CLASSIC_NAME = 'Midnite Classic'

CONEXT_MODBUS_ADDR = 10
CONEXT_GW_IP = '192.168.2.227'
CONEXT_GW_PORT = 503
CONEXT_NAME = 'XW6848'

INFLUXDB_IP = '192.168.1.2'
INFLUXDB_PORT = 8086
INFLUXDB_DB = 'energy'

classic = ModbusControl(MIDNITE_CLASSIC_MODBUS_ADDR, MIDNITE_CLASSIC_IP, MIDNITE_CLASSIC_PORT)
conext = ModbusControl(CONEXT_MODBUS_ADDR, CONEXT_GW_IP, CONEXT_GW_PORT)
influx_client = InfluxDBClient(host=INFLUXDB_IP, port=INFLUXDB_PORT, database=INFLUXDB_DB)

INFLUX_TAG_FIELDS = Dict[str,Union[str,int,float]]
INFLUX_DICT = Dict[str,Union[str,INFLUX_TAG_FIELDS]]

devices = {
    'Midnite Classic': {
        'control': classic,
        'modbus_id': MIDNITE_CLASSIC_MODBUS_ADDR,
        'regmap': MidniteClassic,
        'data': None
    },
    'Conext XW6848': {
        'control': conext,
        'modbus_id': CONEXT_MODBUS_ADDR,
        'regmap': Conext,
        'data': None
    }
}

class SystemState(Enum):
    Waiting_For_Charge = auto()
    Invert = auto()
    Invert_Sell = auto()
    Unknown = auto()

system_state: SystemState = SystemState.Unknown

def control_inverter() -> None:
    """Adjusts inverter settings to optimize solar and battery consumption.
    
    This may be better suited for home automation software such as HomeAssistant,
    but control of such critical components seems logical to keep in a more
    standalone script.
    """
    global system_state

    # Only run if both devices are available
    if devices['Midnite Classic']['data'] is None or devices['Conext XW6848']['data'] is None:
        return
    
    # Recall some key parameters
    soc = devices['Midnite Classic']['data']['fields']['battery_soc']
    watts = devices['Midnite Classic']['data']['fields']['watts']
    maximum_sell_amps = devices['Conext XW6848']['data']['fields']['maximum_sell_amps']
    grid_support = devices['Conext XW6848']['data']['fields']['grid_support']
    grid_support_voltage = devices['Conext XW6848']['data']['fields']['grid_support_voltage']
    v_batt = devices['Midnite Classic']['data']['fields']['v_batt']

    # Manage state transitions
    try:
        # Increase sell power if there is excess sun
        if grid_support == 'Enable' and v_batt > 56 and soc > 85:
            conext.connect()
            conext.set_register(Conext.maximum_sell_amps, maximum_sell_amps + 1)
            system_state = SystemState.Invert_Sell
        # Decrease sell power if we don't have excess power
        elif grid_support == 'Enable' and maximum_sell_amps > 0 and v_batt < 55:
            conext.connect()
            conext.set_register(Conext.maximum_sell_amps, maximum_sell_amps - 1)
        # Stop inverting if battery SOC is too low
        elif grid_support == 'Enable' and soc < 60:
            conext.connect()
            conext.set_register(Conext.grid_support, BinaryState.Disable)
            system_state = SystemState.Waiting_For_Charge
        # Start inverting again if the batteries are mostly charged
        elif grid_support == 'Disable' and soc > 75:
            conext.connect()
            conext.set_register(Conext.grid_support, BinaryState.Enable)
            conext.set_register(Conext.grid_support_voltage, 47)
            conext.set_register(Conext.maximum_sell_amps, 0)
            system_state = SystemState.Invert
    # Never fail
    except Exception as e:
        print(f"Failed to adjust state transition: {e}")
    finally:
        conext.disconnect()


def process_data(signum, _) -> None:
    """Reads all registers from the inverter and charge controller."""
    global system_state
    global devices

    print("Processing...")
    json_body = []
    # Read holding registers from all devices
    for device in devices:
        ctrl = devices[device]['control']
        regmap = devices[device]['regmap']
        # Reset the value map
        devices[device]['data'] = None
        try:
            ctrl.connect()
            devices[device]['data'] = {
                "measurement": device,
                "tags": {
                    "modbus_id": devices[device]['modbus_id']
                },
                "fields": {
                    f.name: ctrl.get_register(f.default) for f in dataclasses.fields(regmap)
                }
            }
            json_body.append(devices[device]['data'])
        # Never fail
        except Exception as e:
            print(f"Unable to process data from {device}: {e}")
        finally:
            ctrl.disconnect()
    # Transmit data to influxdb
    if len(json_body) > 0:
        # Add in the inverter state
        json_body.append(
            {
                "measurement": "System",
                "fields": {
                    "state": system_state._name_
                }
            }
        )
        print("Sending points to influxdb...")
        influx_client.write_points(json_body)
    # Do some logic
    control_inverter()


if __name__ == '__main__':
    # Create a timer to process data every 10 seconds
    signal.signal(signal.SIGALRM, process_data)
    timer_start_delay = 10 - (datetime.now().second % 10)
    signal.setitimer(signal.ITIMER_REAL, timer_start_delay, 10)

    while True:
        # Sleep for an arbitrary amount of time to idle the program
        time.sleep(1)
