#!/usr/bin/env python3

from modbus_control import ModbusControl
from conext_regmap import Conext
from midnite_classic_regmap import MidniteClassic

from influxdb import InfluxDBClient

import dataclasses
import signal
import time
from datetime import datetime

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

devices = {
    'Midnite Classic': {
        'control': classic,
        'modbus_id': MIDNITE_CLASSIC_MODBUS_ADDR,
        'regmap': MidniteClassic
    },
    'Conext XW6848': {
        'control': conext,
        'modbus_id': CONEXT_MODBUS_ADDR,
        'regmap': Conext
    }
}

def process_data(signum, _):
    print("Processing...")
    json_body = []
    # Read holding registers from all devices
    for device in devices:
        ctrl = devices[device]['control']
        regmap = devices[device]['regmap']
        try:
            ctrl.connect()
            json_body.append(
                {
                    "measurement": device,
                    "tags": {
                        "modbus_id": devices[device]['modbus_id']
                    },
                    "fields": {
                        f.name: ctrl.get_register(f.default) for f in dataclasses.fields(regmap)
                    }
                }
            )
        except Exception as e:
            print(f"Unable to process data from {device}: {e}.")
        finally:
            ctrl.disconnect()
    # Transmit data to influxdb
    if len(json_body) > 0:
        print("Sending points to influxdb...")
        influx_client.write_points(json_body)

# Create a timer to process data every 10 seconds
signal.signal(signal.SIGALRM, process_data)
timer_start_delay = 10 - (datetime.now().second % 10)
signal.setitimer(signal.ITIMER_REAL, timer_start_delay, 10)

while True:
    # Sleep for an arbitrary amount of time to idle the program
    time.sleep(1)