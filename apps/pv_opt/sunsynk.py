import json
import time
from abc import ABC, abstractmethod
from time import sleep

import numpy as np
import pandas as pd

TIMEFORMAT = "%H:%M"

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
        # Brand Configuration: Exposed as inverter.brand_config and can be over-written using arguments
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
    "SUNSYNK_SOLARSUNSYNK": {
        "online": "sensor.state_of_charge",
        "default_config": {
            "maximum_dod_percent": 20,
            "id_battery_soc": "sensor.state_of_charge",
            "id_consumption_today": "sensor.total_load",
            "id_consumption": "sensor.instantaneous_load",
            "id_grid_import_today": "sensor.grid_to_load",
            "id_grid_export_today": "sensor.solar_to_grid",
            "id_solar_power": [
                "sensor.instantaneous_ppv1",
                "sensor.instantaneous_ppv2",
            ],
            "supports_hold_soc": False,
            "update_cycle_seconds": 60,
        },
        # Brand Configuration: Exposed as inverter.brand_config and can be over-written using arguments
        # from the config.yaml file but not required outside of this module
        "brand_config": {
            "battery_voltage": "sensor.instantaneous_battery_i_o",
            "battery_current": "sensor.instantaneous_battery_i_o",
            "inverter_serial": "",
            "id_use_timer": "sensor.setting_average_state_of_charge_capacity",
            "id_priority_load": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_charge_start": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_charge_end": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_charge_enable": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_charge_capacity": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_discharge_start": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_discharge_end": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_dicharge_enable": "sensor.setting_average_state_of_charge_capacity",
            "id_timed_discharge_capacity": "sensor.setting_average_state_of_charge_capacity",
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


def create_inverter_controller(inverter_type: str, host):
    """Factory function to create the correct inverter controller."""
    if inverter_type == "SUNSYNK_SOLARSYNKV3":
        return SolarSynkV3Inverter(inverter_type=inverter_type, host=host)
    elif inverter_type == "SUNSYNK_SOLARSUNSYNK":
        return SolarSunsynkInverter(inverter_type=inverter_type, host=host)
    else:
        host.log(f"Unknown inverter type {inverter_type}", level="ERROR")
        return False


class SunsynkInverterController(ABC):
    """Abstract base class for all Sunsynk inverter controllers."""

    def __init__(self, inverter_type: str, host) -> None:
        self._host = host
        self.tz = self._host.tz
        if host is not None:
            self.log = host.log
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

    def _convert_kwargs(self, kwargs: dict) -> dict:
        """Convert numpy/pandas types to native Python types."""
        converted = {}
        for key, value in kwargs.items():
            if isinstance(value, (np.integer, np.int64)):
                converted[key] = int(value)
            elif isinstance(value, (np.floating, np.float64)):
                converted[key] = float(value)
            elif isinstance(value, np.ndarray):
                converted[key] = value.tolist()
            elif isinstance(value, np.datetime64):
                converted[key] = pd.Timestamp(value).strftime("%H:%M")
            elif isinstance(value, np.timedelta64):
                converted[key] = str(value)
            elif isinstance(value, pd.Timestamp):
                converted[key] = value.strftime("%H:%M")
            elif isinstance(value, pd.Timedelta):
                converted[key] = str(value)
            else:
                converted[key] = value
        return converted

    @abstractmethod
    def _set_inverter(self, **kwargs):
        """Send settings to the inverter. Implemented by each subclass."""
        pass

    @abstractmethod
    def enable_timed_mode(self):
        pass

    @abstractmethod
    def control_charge(self, enable, **kwargs):
        pass

    @abstractmethod
    def control_discharge(self, enable, **kwargs):
        pass

    @abstractmethod
    def hold_soc(self, enable, soc=None):
        pass

    @property
    @abstractmethod
    def status(self):
        pass

    def _monitor_target_soc(self, target_soc, mode="charge"):
        pass


class SunsynkBaseInverter(SunsynkInverterController):
    """Shared implementation of charge/discharge/hold logic for all Sunsynk inverters.

    Subclasses implement _set_inverter() to handle the actual write mechanism.
    """

    def enable_timed_mode(self):
        self.log("Entered enable_timed_mode")
        self.log(f"self._config = {self._config}")

        params = {
            self._brand_config["json_use_timer"]: 1,
            self._brand_config["json_priority_load"]: 1,
        }
        self._set_inverter(**params)

        params = {x: "00:00" for x in self._brand_config["json_timed_unused"]}
        self._set_inverter(**params)

    def hold_soc(self, enable, soc=None):
        pass

    @property
    def status(self):
        time_now = pd.Timestamp.now(tz=self.tz)
        charge_start = pd.Timestamp(self._host.get_config("id_timed_charge_start"), tz=self.tz)
        charge_end = pd.Timestamp(self._host.get_config("id_timed_charge_end"), tz=self.tz)
        discharge_start = pd.Timestamp(self._host.get_config("id_timed_discharge_start"), tz=self.tz)
        discharge_end = pd.Timestamp(self._host.get_config("id_timed_discharge_end"), tz=self.tz)

        return {
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


class SolarSynkV3Inverter(SunsynkBaseInverter):
    """Controller for the martinville/solarsynkv3 Home Assistant Add-On.

    Writes settings via an input_text helper entity in v2# semicolon-delimited
    format. The Add-On polls the helper on its refresh interval (~5 minutes),
    sends the accumulated settings to the Sunsynk cloud, then clears the helper.
    FIFO merging ensures multiple writes between polls are not lost.
    Multiple _set_inverter calls are required because battery and system mode
    settings must be sent as separate writes, and the v2# format has a 255
    character limit per write.
    """

    def control_charge(self, enable, **kwargs):
        time_now = pd.Timestamp.now(tz=self.tz)

        if enable:
            params = {
                self._brand_config["json_work_mode"]: 2,
                self._brand_config["json_timed_charge_target_soc"]: kwargs.get("target_soc", 100),
                self._brand_config["json_timed_charge_start"]: kwargs.get(
                    "start", time_now.strftime(TIMEFORMAT)
                ),
                self._brand_config["json_timed_charge_end"]: kwargs.get(
                    "end", time_now.ceil("30min").strftime(TIMEFORMAT)
                ),
                self._brand_config["json_charge_current"]: min(
                    round(kwargs.get("power", 0) / self._host.get_config("battery_voltage")),
                    self._host.get_config("battery_current_limit_amps"),
                ),
            }
            self._set_inverter(**params)

            params = {
                self._brand_config["json_timed_charge_enable"]: True,
                self._brand_config["json_gen_charge_enable"]: False,
            }
            self._set_inverter(**params)

        else:
            params = {
                self._brand_config["json_work_mode"]: 2,
                self._brand_config["json_timed_charge_target_soc"]: 100,
                self._brand_config["json_timed_charge_start"]: "00:00",
                self._brand_config["json_timed_charge_end"]: "00:00",
                self._brand_config["json_charge_current"]: self._host.get_config(
                    "battery_current_limit_amps"
                ),
            }
            self._set_inverter(**params)

            params = {
                self._brand_config["json_timed_charge_enable"]: False,
                self._brand_config["json_gen_charge_enable"]: True,
            }
            self._set_inverter(**params)

    def control_discharge(self, enable, **kwargs):
        time_now = pd.Timestamp.now(tz=self.tz)

        if enable:
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
            self._set_inverter(**params)

            params = {
                self._brand_config["json_timed_discharge_power"]: kwargs.get("power", 0),
                self._brand_config["json_timed_discharge_enable"]: True,
                self._brand_config["json_gen_discharge_enable"]: False,
            }
            self._set_inverter(**params)

        else:
            params = {
                self._brand_config["json_work_mode"]: 2,
                self._brand_config["json_timed_discharge_target_soc"]: 100,
                self._brand_config["json_timed_discharge_start"]: "00:00",
                self._brand_config["json_timed_discharge_end"]: "00:00",
                self._brand_config["json_timed_discharge_power"]: 0,
            }
            self._set_inverter(**params)

            params = {
                self._brand_config["json_timed_discharge_enable"]: False,
                self._brand_config["json_gen_discharge_enable"]: True,
            }
            self._set_inverter(**params)

    def _set_inverter(self, **kwargs):
        converted = self._convert_kwargs(kwargs)

        entity_id = self._host.config.get("id_control_helper", None)
        if entity_id is not None:
            # Force a fresh state read from HA, bypassing AppDaemon's cache
            self._host.call_service("homeassistant/update_entity", entity_id=entity_id)
            current_state = self._host.get_state(entity_id)
            try:
                # Parse any pending v2# settings already in the helper (FIFO merge)
                if current_state not in [None, ""] and current_state.startswith("v2#"):
                    current_dict = dict(
                        pair.split(":", 1)
                        for pair in current_state[3:].split(";")
                        if ":" in pair
                    )
                else:
                    current_dict = {}
            except Exception:
                self.log("Error parsing current helper state, starting fresh")
                current_dict = {}
        else:
            self.log(f"Entity not detected, entity_id read was {entity_id}")
            current_dict = {}

        # Merge pending settings with new ones and serialise to v2# format
        updated_dict = current_dict | converted
        new_value = "v2#" + ";".join(f"{k}:{v}" for k, v in updated_dict.items())

        self.log(f"Setting SolarSynk input helper {entity_id} to {new_value}")
        #  self._host.call_service("input_text/set_value", entity_id=entity_id, value=new_value)


class SolarSunsynkInverter(SunsynkBaseInverter):
    """Controller for the MorneSaunders360/Solar-Sunsynk HACS integration.

    Writes settings by calling the solar_sunsynk.set_solar_settings HA service
    directly, providing real-time inverter control with no intermediate helper
    entity or polling delay. Partial parameter sets are supported — only the
    fields being changed need to be supplied. All settings for a charge or
    discharge command are sent in a single service call.
    """

    def control_charge(self, enable, **kwargs):
        time_now = pd.Timestamp.now(tz=self.tz)

        if enable:
            params = {
                self._brand_config["json_work_mode"]: 2,
                self._brand_config["json_timed_charge_target_soc"]: kwargs.get("target_soc", 100),
                self._brand_config["json_timed_charge_start"]: kwargs.get(
                    "start", time_now.strftime(TIMEFORMAT)
                ),
                self._brand_config["json_timed_charge_end"]: kwargs.get(
                    "end", time_now.ceil("30min").strftime(TIMEFORMAT)
                ),
                self._brand_config["json_charge_current"]: min(
                    round(kwargs.get("power", 0) / self._host.get_config("battery_voltage")),
                    self._host.get_config("battery_current_limit_amps"),
                ),
                self._brand_config["json_timed_charge_enable"]: True,
                self._brand_config["json_gen_charge_enable"]: False,
            }
        else:
            params = {
                self._brand_config["json_work_mode"]: 2,
                self._brand_config["json_timed_charge_target_soc"]: 100,
                self._brand_config["json_timed_charge_start"]: "00:00",
                self._brand_config["json_timed_charge_end"]: "00:00",
                self._brand_config["json_charge_current"]: self._host.get_config(
                    "battery_current_limit_amps"
                ),
                self._brand_config["json_timed_charge_enable"]: False,
                self._brand_config["json_gen_charge_enable"]: True,
            }

        self._set_inverter(**params)

    def control_discharge(self, enable, **kwargs):
        time_now = pd.Timestamp.now(tz=self.tz)

        if enable:
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
                self._brand_config["json_timed_discharge_power"]: kwargs.get("power", 0),
                self._brand_config["json_timed_discharge_enable"]: True,
                self._brand_config["json_gen_discharge_enable"]: False,
            }
        else:
            params = {
                self._brand_config["json_work_mode"]: 2,
                self._brand_config["json_timed_discharge_target_soc"]: 100,
                self._brand_config["json_timed_discharge_start"]: "00:00",
                self._brand_config["json_timed_discharge_end"]: "00:00",
                self._brand_config["json_timed_discharge_power"]: 0,
                self._brand_config["json_timed_discharge_enable"]: False,
                self._brand_config["json_gen_discharge_enable"]: True,
            }

        self._set_inverter(**params)

    def _set_inverter(self, **kwargs):
        converted = self._convert_kwargs(kwargs)
        sn = self._brand_config.get("inverter_serial")
        self.log(
            f"Calling solar_sunsynk.set_solar_settings for inverter {sn} with {converted}"
        )
        self._host.call_service(
            "solar_sunsynk/set_solar_settings",
            sn=sn,
            **converted,
        )


# Legacy compatibility: InverterController is kept as an alias so any existing
# code that instantiates InverterController directly continues to work.
# New code should use create_inverter_controller() instead.
class InverterController(SunsynkBaseInverter):
    """Legacy entry point — delegates to SunsynkBaseInverter.

    Use create_inverter_controller() for new integrations.
    """

    def _set_inverter(self, **kwargs):
        if self._type == "SUNSYNK_SOLARSUNSYNK":
            SolarSunsynkInverter._set_inverter(self, **kwargs)
        else:
            SolarSynkV3Inverter._set_inverter(self, **kwargs)
