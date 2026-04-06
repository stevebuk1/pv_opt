import json
import time
from time import sleep
from typing import final

import numpy as np
import pandas as pd

TIMEFORMAT = "%H:%M"

READ_SENSOR_RETRIES = 10

INVERTER_DEFS = {
    "SUNSYNK_SOLARSYNKV3": {
        "online": "sensor.{device_name}_{inverter_sn}_battery_soc",
        "default_config": {
            "maximum_dod_percent": 20,
            "id_battery_soc": "sensor.{device_name}_{inverter_sn}_battery_soc",
            "id_consumption_today": "sensor.{device_name}_{inverter_sn}_day_load_energy",
            "id_consumption": "sensor.{device_name}_{inverter_sn}_load_power",
            "id_grid_import_today": "sensor.{device_name}_{inverter_sn}_day_grid_import",
            "id_grid_export_today": "sensor.{device_name}_{inverter_sn}_day_grid_export",
            "id_solar_power": [
                "sensor.{device_name}_{inverter_sn}_pv1_power",
                "sensor.{device_name}_{inverter_sn}_pv2_power",
            ],
            "supports_hold_soc": False,
            "update_cycle_seconds": 300,
        },
        # Brand Conguration: Exposed as inverter.brand_config and can be over-written using arguments
        # from the config.yaml file but not required outside of this module
        "brand_config": {
            "battery_voltage": "sensor.{device_name}_{inverter_sn}_battery_voltage",
            "battery_current": "sensor.{device_name}_{inverter_sn}_battery_current",
            "id_control_helper": "input_text.{device_name}_{inverter_sn}_settings",
            "id_use_timer": "sensor.{device_name}_{inverter_sn}_use_timer",
            "id_priority_load": "sensor.{device_name}_{inverter_sn}_priority_load",
            "id_timed_charge_start": "sensor.{device_name}_{inverter_sn}_prog1_time",
            "id_timed_charge_end": "sensor.{device_name}_{inverter_sn}_prog2_time",
            "id_timed_charge_enable": "sensor.{device_name}_{inverter_sn}_prog1_charge",
            "id_timed_charge_capacity": "sensor.{device_name}_{inverter_sn}_prog1_capacity",
            "id_timed_discharge_start": "sensor.{device_name}_{inverter_sn}_prog3_time",
            "id_timed_discharge_end": "sensor.{device_name}_{inverter_sn}_prog4_time",
            "id_timed_dicharge_enable": "sensor.{device_name}_{inverter_sn}_prog3_charge",
            "id_timed_discharge_capacity": "sensor.{device_name}_{inverter_sn}_prog3_capacity",
            "json_work_mode": "sysWorkMode",
            "json_priority_load": "energyMode",
            "json_grid_charge": "sdChargeOn",
            "json_use_timer": "peakAndVallery",
            "json_timed_charge_start": "sellTime1",
            "json_timed_charge_end": "sellTime2",
            "json_timed_unused": [f"sellTime{i}" for i in range(5, 7)],
            "json_timed_charge_enable": "time1on",
            "json_timed_charge_target_soc": "cap1",
            "json_charge_current": "sdBatteryCurrent",
            "json_gen_charge_enable": "genTime1on",
            "json_timed_discharge_start": "sellTime3",
            "json_timed_discharge_end": "sellTime4",
            "json_timed_discharge_enable": "time3on",
            "json_timed_discharge_target_soc": "cap3",
            "json_timed_discharge_power": "sellTime3Pac",
            "json_gen_discharge_enable": "genTime3on",
        },
    },
}


class InverterController:
    def __init__(self, inverter_type: str, host) -> None:
        self._host = host
        self.tz = self._host.tz
        if host is not None:
            self.log = host.log
        #    self.config = self._host.config
        self._type = inverter_type
        self._device_name = self._host.device_name
        self._inverter_sn = self._host.inverter_sn
        self._config = {}
        self._brand_config = {}
        self._online = INVERTER_DEFS[self._type]["online"].replace("{device_name}", self._device_name)
        for defs, conf in zip(
            [INVERTER_DEFS[self._type][x] for x in ["default_config", "brand_config"]],
            [self._config, self._brand_config],
        ):
            for item in defs:
                if isinstance(defs[item], str):
                    temp = defs[item].replace("{device_name}", self._device_name)
                    conf[item] = temp.replace("{inverter_sn}", self._inverter_sn)
                elif isinstance(defs[item], list):
                    y = [z.replace("{device_name}", self._device_name) for z in defs[item]]
                    conf[item] = [x.replace("{inverter_sn}", self._inverter_sn) for x in y]
                else:
                    conf[item] = defs[item]
        self.log(f"Loading controller for inverter type {self._type}")

    @property
    # def is_online(self):
    #    entity_id = INVERTER_DEFS[self.type].get("online", (None, None))
    #    if entity_id is not None:
    #        entity_id = entity_id.replace("{device_name}", self._device_name)
    #        return self._host.get_state(entity_id) not in [
    #            "unknown", "unavailable"]
    #    else:
    #        return True
    def is_online(self):
        entity_id = self._online
        if entity_id is not None:
            return self._host.get_state_retry(entity_id) not in [
                "unknown",
                "unavailable",
            ]
        else:
            return False

    @property
    def config(self):
        return self._config

    @property
    def brand_config(self):
        return self._brand_config

    @property
    def timed_mode(self):
        return True

    def clear_hold_status(self):
        pass

    def _unknown_inverter(self):
        e = f"Unknown inverter type {self._type}"
        self.log(e, level="ERROR")
        self._host.status(e)
        raise Exception(e)

    def _solarsynk_set_helper(self, **kwargs):
        if self._host.get_config("id_control_helper") is not None:
            self.log("About to read Json")
            current_json = json.loads(self._host.get_config("id_control_helper"))
        else:
            current_json = {}

        # Convert numpy/pandas types to native Python types

        converted_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, (np.integer, np.int64)):
                converted_kwargs[key] = int(value)
            elif isinstance(value, (np.floating, np.float64)):
                converted_kwargs[key] = float(value)
            elif isinstance(value, np.ndarray):
                converted_kwargs[key] = value.tolist()
            elif isinstance(value, np.datetime64):
                converted_kwargs[key] = pd.Timestamp(value).strftime("%H:%M")
            elif isinstance(value, np.timedelta64):
                converted_kwargs[key] = str(value)
            elif isinstance(value, pd.Timestamp):  # pd not expected but added for completeness
                converted_kwargs[key] = value.strftime("%H:%M")
            elif isinstance(value, pd.Timedelta):
                converted_kwargs[key] = str(value)
            else:
                converted_kwargs[key] = value

        updated_json = current_json | converted_kwargs
        new_json = json.dumps(updated_json)

        # entity_id = self._host.config("id_control_helper")
        self.log("About to get entity id")
        entity_id = self._host.config.get("id_control_helper", None)

        self.log(f"Setting SolarSynk input helper {entity_id} to {new_json}")
        #  self._host.set_state(entity_id=entity_id, state=new_json)

        # Wait until text input helper is empty (i.e is written to the Cloud)
        # Max wait time of 10 seconds
        empty = False
        retries = 0
        while not empty and retries < READ_SENSOR_RETRIES:
            retries += 1
            time.sleep(1)
            self.log(f"Checking for {entity_id} to be empty")
            content = self._host.get_state_retry(entity_id=entity_id)
            empty = content == None

    def enable_timed_mode(self):
        self.log("Entered enable_timed_mode")
        self.log(f"self._config = {self._config}")
        if self._type == "SUNSYNK_SOLARSYNKV3":
            params = {
                self._brand_config["json_use_timer"]: 1,
                self._brand_config["json_priority_load"]: 1,
            }
            self._solarsynk_set_helper(**params)

            params = {x: "00:00" for x in self._brand_config["json_timed_unused"]}

            self._solarsynk_set_helper(**params)

        else:
            self._unknown_inverter()

    def control_charge(self, enable, **kwargs):
        if self._type == "SUNSYNK_SOLARSYNKV3":
            time_now = pd.Timestamp.now(tz=self.tz)

            if enable:
                # self.enable_timed_mode()

                params = {
                    self._brand_config["json_work_mode"]: 2,
                    self._brand_config["json_timed_charge_target_soc"]: kwargs.get("target_soc", 100),
                    self._brand_config["json_timed_charge_start"]: kwargs.get("start", time_now.strftime(TIMEFORMAT)),
                    self._brand_config["json_timed_charge_end"]: kwargs.get(
                        "end", time_now.ceil("30min").strftime(TIMEFORMAT)
                    ),
                    self._brand_config["json_charge_current"]: min(
                        round(kwargs.get("power", 0) / self._host.get_config("battery_voltage")),
                        self._host.get_config("battery_current_limit_amps"),
                    ),
                }

                self._solarsynk_set_helper(**params)

                params = {
                    self._brand_config["json_timed_charge_enable"]: True,
                    self._brand_config["json_gen_charge_enable"]: False,
                }

                self._solarsynk_set_helper(**params)

            else:
                params = {
                    self._brand_config["json_work_mode"]: 2,
                    self._brand_config["json_timed_charge_target_soc"]: 100,
                    self._brand_config["json_timed_charge_start"]: "00:00",
                    self._brand_config["json_timed_charge_end"]: "00:00",
                    self._brand_config["json_charge_current"]: self._host.get_config("battery_current_limit_amps"),
                }

                self._solarsynk_set_helper(**params)

                params = {
                    self._brand_config["json_timed_charge_enable"]: False,
                    self._brand_config["json_gen_charge_enable"]: True,
                }

                self._solarsynk_set_helper(**params)

        else:
            self._unknown_inverter()

    def control_discharge(self, enable, **kwargs):
        if self._type == "SUNSYNK_SOLARSYNKV3":
            time_now = pd.Timestamp.now(tz=self.tz)

            if enable:
                # self.enable_timed_mode()
                params = {
                    self._brand_config["json_work_mode"]: 0,
                    self._brand_config["json_timed_discharge_target_soc"]: kwargs.get(
                        "target_soc", self._host.get_config("maximum_dod_percent")
                    ),
                    self._brand_config["json_timed_discharge_start"]: kwargs.get(
                        "start", time_now.strftime(TIMEFORMAT)
                    ),
                    self._brand_config["json_timed_discharge_end"]: kwargs.get(
                        "end", time_now.ceil("30min").strftime(TIMEFORMAT)
                    ),
                }

                self._solarsynk_set_helper(**params)

                params = {
                    self._brand_config["json_timed_discharge_power"]: kwargs.get("power", 0),
                    self._brand_config["json_timed_discharge_enable"]: True,
                    self._brand_config["json_gen_discharge_enable"]: False,
                }

                self._solarsynk_set_helper(**params)

            else:
                params = {
                    self._brand_config["json_work_mode"]: 2,
                    self._brand_config["json_timed_discharge_target_soc"]: 100,
                    self._brand_config["json_timed_discharge_start"]: "00:00",
                    self._brand_config["json_timed_discharge_end"]: "00:00",
                    self._brand_config["json_timed_discharge_power"]: 0,
                }

                self._solarsynk_set_helper(**params)

                params = {
                    self._brand_config["json_timed_discharge_enable"]: False,
                    self._brand_config["json_gen_discharge_enable"]: True,
                }

                self._solarsynk_set_helper(**params)
        else:
            self._unknown_inverter()

    def hold_soc(self, enable, soc=None):
        if self._type == "SUNSYNK_SOLARSYNKV3":
            pass

        else:
            self._unknown_inverter()

    @property
    def status(self):
        status = None
        time_now = pd.Timestamp.now(tz=self.tz)

        if self._type == "SUNSYNK_SOLARSYNKV3":
            charge_start = pd.Timestamp(self._host.get_config("id_timed_charge_start"), tz=self.tz)
            charge_end = pd.Timestamp(self._host.get_config("id_timed_charge_end"), tz=self.tz)
            discharge_start = pd.Timestamp(self._host.get_config("id_timed_charge_start"), tz=self.tz)
            discharge_end = pd.Timestamp(self._host.get_config("id_timed_charge_end"), tz=self.tz)

            status = {
                "timer mode": self._host.get_config("id_use_timer"),
                "priority load": self._host.get_config("id_priority_load"),
                "charge": {
                    "start": charge_start,
                    "end": charge_end,
                    "active": self._host.get_config("id_timed_charge_enable")
                    and (time_now >= charge_start)
                    and (time_now < charge_end),
                    "target_soc": self._host.get_config("id_timed_charge_target_soc"),
                },
                "discharge": {
                    "start": discharge_start,
                    "end": discharge_end,
                    "active": self._host.get_config("id_timed_discharge_enable")
                    and (time_now >= discharge_start)
                    and (time_now < discharge_end),
                    "target_soc": self._host.get_config("id_timed_discharge_target_soc"),
                },
                "hold_soc": {
                    "active": False,
                    "soc": 0.0,
                },
            }

            return status

        else:
            self._unknown_inverter()

    def _monitor_target_soc(self, target_soc, mode="charge"):
        pass
