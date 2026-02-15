#!/usr/bin/env python3

from modbus_control import ModbusControl
from conext_regmap import Conext, BinaryState
from midnite_classic_regmap import MidniteClassic
from system_manager import SystemManager, DeviceInfo, DATA_FIELDS

from influxdb import InfluxDBClient
import paho.mqtt.publish

import datetime
import time
from typing import Dict, Optional
from enum import Enum, auto
import logging

CLASSIC_MODBUS_ADDR = 1
CLASSIC_IP = '192.168.1.10'
CLASSIC_PORT = 502
CLASSIC_NAME = 'Midnite Classic'

CONEXT_MODBUS_ADDR = 10
CONEXT_GW_IP = '192.168.1.11'
CONEXT_GW_PORT = 503
CONEXT_NAME = 'Conext XW6848'

INFLUXDB_IP = '192.168.1.2'
INFLUXDB_PORT = 8086
INFLUXDB_DB = 'energy'

MQTT_IP = '192.168.1.2'
MQTT_PORT = 1883
MQTT_SOLAR_PRODUCTION_TOPIC = "mppt/pv_production_w"
MPPT_GRID_EXPORT_TOPIC = "mppt/grid_export_w"

logging.basicConfig(level=logging.INFO)

classic = ModbusControl(CLASSIC_MODBUS_ADDR, CLASSIC_IP, CLASSIC_PORT)
conext = ModbusControl(CONEXT_MODBUS_ADDR, CONEXT_GW_IP, CONEXT_GW_PORT)
influx_client = InfluxDBClient(host=INFLUXDB_IP, port=INFLUXDB_PORT, database=INFLUXDB_DB)

class SystemState(Enum):
    Waiting_For_Charge = auto()
    Invert = auto()
    Invert_Sell = auto()
    Unknown = auto()

class InverterStateMachine:

    system_state = SystemState.Unknown
    state_change_time = time.time()

    def __init__(self, influx_client: Optional[InfluxDBClient], send_mqtt: bool = False) -> None:
        self.influx_client = influx_client
        self.send_mqtt = send_mqtt
        self.evse_offset = 0
        self.logger = logging.getLogger(self.__class__.__name__)

    def update_state(self, state: SystemState) -> None:
        """Writes system state to influxdb."""

        self.logger.info(f"Changing system state to {state._name_}")
        self.system_state = state
        self.state_change_time = time.time()

        if self.influx_client:
            json_body = [
                {
                    "measurement": "System",
                    "fields": {
                        "state": self.system_state._name_
                    }
                }
            ]
            self.influx_client.write_points(json_body)

    def detect_initial_state(self, grid_support: str, maximum_sell_amps: float) -> SystemState:
        """Tries to determine what the current system state is."""

        if grid_support == 'Disable':
            return SystemState.Waiting_For_Charge
        elif maximum_sell_amps == 0:
            return SystemState.Invert
        elif maximum_sell_amps > 0:
            return SystemState.Invert_Sell

        return SystemState.Unknown

    def control_inverter(self, data_dict: Dict[str,DATA_FIELDS]) -> None:
        """Adjusts inverter settings to optimize solar and battery consumption.
        
        This may be better suited for home automation software such as HomeAssistant,
        but control of such critical components seems logical to keep in a more
        standalone script.
        """

        # Only run if both devices are available
        if data_dict[CLASSIC_NAME] is None or data_dict[CONEXT_NAME] is None:
            return
        
        # Recall some key parameters
        soc = data_dict[CLASSIC_NAME]['battery_soc']
        watts = data_dict[CLASSIC_NAME]['watts']
        maximum_sell_amps = data_dict[CONEXT_NAME]['maximum_sell_amps']
        grid_support = data_dict[CONEXT_NAME]['grid_support']
        grid_output_power = data_dict[CONEXT_NAME]['grid_output_power']
        load_ac_power = data_dict[CONEXT_NAME]['load_ac_power']
        invert_dc_power = data_dict[CONEXT_NAME]['invert_dc_power']
        v_batt = data_dict[CLASSIC_NAME]['v_batt']
        inverter_status = data_dict[CONEXT_NAME]['inverter_status']
        combo_charge_stage = data_dict[CLASSIC_NAME]['combo_charge_stage']

        # If state is unknown, figure out what the active state is
        if self.system_state == SystemState.Unknown:
            self.system_state = self.detect_initial_state(grid_support, maximum_sell_amps)
            self.logger.info(f"Initial state appears to be {self.system_state._name_}")
            self.update_state(self.system_state)

        # Monday after 5PM
        recovery_time = datetime.datetime.today().weekday() == 0 and datetime.datetime.now().hour >= 17

        # Manage state transitions
        try:
            # Start selling if it's sunny and it has been 1 minute since the last state transition
            if self.system_state == SystemState.Invert and v_batt > 56 and (time.time() - self.state_change_time > 240):
                conext.connect()
                conext.set_register(Conext.grid_support_voltage, 55.6)
                conext.set_register(Conext.maximum_sell_amps, 21)
                self.update_state(SystemState.Invert_Sell)

            # Stop selling if we don't have excess power, with a 500W buffer to account for transient loads
            if self.system_state == SystemState.Invert_Sell and (watts < (load_ac_power-500) or inverter_status == 'AC_Pass_Through'):
                conext.connect()
                conext.set_register(Conext.grid_support_voltage, 47)
                conext.set_register(Conext.maximum_sell_amps, 0)
                self.update_state(SystemState.Invert)
            # Stop inverting if battery SOC is too low or it is recovery time
            elif grid_support == 'Enable' and (soc < 60 or recovery_time):
                conext.connect()
                conext.set_register(Conext.grid_support, BinaryState.Disable)
                self.update_state(SystemState.Waiting_For_Charge)
            # Start inverting again if the charge controller is in absorb state
            elif grid_support == 'Disable' and combo_charge_stage == 'Absorb' and soc > 90 and not recovery_time:
                conext.connect()
                conext.set_register(Conext.grid_support, BinaryState.Enable)
                conext.set_register(Conext.grid_support_voltage, 47)
                conext.set_register(Conext.maximum_sell_amps, 0)
                self.update_state(SystemState.Invert)
        # Never fail
        except (ValueError, ConnectionError) as e:
            self.logger.warning(f"Failed to perform state transition: {e}")
        finally:
            conext.disconnect()

        # Publish solar panel power on MQTT for openEVSE
        if self.send_mqtt:
            try:
                paho.mqtt.publish.single(
                    topic=MQTT_SOLAR_PRODUCTION_TOPIC, 
                    payload=grid_output_power, 
                    hostname=MQTT_IP, 
                    port=MQTT_PORT
                )
            except:
                self.logger.warning("Failed to publish MQTT message.")   

if __name__ == '__main__':
    devices = [
        DeviceInfo(name=CLASSIC_NAME, control=classic, regmap=MidniteClassic),
        DeviceInfo(name=CONEXT_NAME, control=conext, regmap=Conext)
    ]
    manager = SystemManager(devices, influx_client)
    state_machine = InverterStateMachine(influx_client, send_mqtt = True)
    manager.add_callback(state_machine.control_inverter)
    # Start a timer with a 10 second period for monitoring the system
    manager.start()

    # Idle forever
    while True:
        time.sleep(1)
