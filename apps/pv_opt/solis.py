import time
from abc import ABC, abstractmethod
from time import sleep
from typing import final

import pandas as pd

LIMITS = ["start", "end"]
DIRECTIONS = ["charge", "discharge"]
TIME_UNITS = ["hours", "minutes"]


URLS = {
    "root": "https://www.soliscloud.com:13333",
    "login": "/v2/api/login",
    "control": "/v2/api/control",
    "inverterList": "/v1/api/inverterList",
    "atRead": "/v2/api/atRead",
}

SOLIS_DEFAULT_CODES = {
    True: {
        "Self-Use - No Grid Charging": 1,
        "Backup/Reserve - No Grid Charging": 17,
        "Self-Use": 33,
        "Off-Grid Mode": 37,
        "Battery Awaken": 41,
        "Backup/Reserve": 49,
        "Feed-in priority - No Grid Charging": 64,
        "Feed-in priority": 96,
    },
    False: {
        "Selfuse - No Grid Charging": 1,
        "Self-Use - No Grid Charging": 1,
        "Timed Charge/Discharge - No Grid Charging": 3,
        "Backup/Reserve - No Grid Charging": 17,
        "Selfuse": 33,
        "Self-Use - No Timed Charge/Discharge": 33,
        "Self-Use": 35,
        "Timed Charge/Discharge": 35,
        "Off-Grid Mode": 37,
        "Battery Awaken": 41,
        "Battery Awaken + Timed Charge/Discharge": 43,
        "Backup/Reserve - No Timed Charge/Discharge": 49,
        "Backup/Reserve": 51,
        "Feed-in priority - No Grid Charging": 64,
        "Feed-in priority - No Timed Charge/Discharge": 96,
        "Feed-in priority": 98,
    },
}

REGISTERS = {
    True: {
        "timed_charge_soc": 43708,
        "timed_charge_current": 43709,
        "timed_charge_start_hours": 43711,
        "timed_charge_start_minutes": 43712,
        "timed_charge_end_hours": 43713,
        "timed_charge_end_minutes": 43714,
        "timed_discharge_soc": 43750,
        "timed_discharge_current": 43151,
        "timed_discharge_start_hours": 43153,
        "timed_discharge_start_minutes": 43154,
        "timed_discharge_end_hours": 43155,
        "timed_discharge_end_minutes": 43156,
        "storage_control_switch": 43110,
        "backup_mode_soc": 43024,
    },
    False: {
        "timed_charge_current": 43141,
        "timed_charge_start_hours": 43143,
        "timed_charge_start_minutes": 43144,
        "timed_charge_end_hours": 43145,
        "timed_charge_end_minutes": 43146,
        "timed_discharge_current": 43142,
        "timed_discharge_start_hours": 43147,
        "timed_discharge_start_minutes": 43148,
        "timed_discharge_end_hours": 43149,
        "timed_discharge_end_minutes": 43150,
        "storage_control_switch": 43110,
        "backup_mode_soc": 43024,
    },
}

SOLIS_BITS = [
    "SelfUse",
    "Timed",
    "OffGrid",
    "BatteryWake",
    "Backup",  # Used for Hold SOC
    "GridCharge",
    "FeedInPriority",
]


TIMEFORMAT = "%H:%M"
INVERTER_DEFS = {
    "SOLIS_SOLAX_MODBUS": {
        "online": "number.{device_name}_battery_minimum_soc",
        "codes": SOLIS_DEFAULT_CODES,
        "bits": [
            "SelfUse",
            "Timed",
            "OffGrid",
            "BatteryWake",
            "Backup",
            "GridCharge",
            "FeedInPriority",
        ],
        # Default Configuration: Exposed as inverter.config and provides defaults for this inverter for the
        # required config. These config items can be over-written by config specified in the config.yaml
        # file. They are required for the main PV_Opt module and if they cannot be found an ERROR will be
        # raised
        # house_load_x and _bypass_load_x are not the defaults for Solax.
        # This is probably intentional, as the datafiles are large and loading kWh is preferred
        "default_config": {
            "maximum_dod_percent": "number.{device_name}_battery_minimum_soc",
            "id_battery_soc": "sensor.{device_name}_battery_soc",
            "id_consumption_today": "sensor.{device_name}_house_load_today",
            "id_consumption": [
                "sensor.{device_name}_house_load_x",
                "sensor.{device_name}_bypass_load_x",
            ],
            "id_grid_import_today": "sensor.{device_name}_grid_import_today",
            "id_grid_export_today": "sensor.{device_name}_grid_export_today",
            "id_battery_charge_power": "sensor.{device_name}_battery_input_energy",
            "id_inverter_ac_power": "sensor.{device_name}_active_power",
            "supports_hold_soc": True,
            "supports_forced_discharge": True,
            "update_cycle_seconds": 15,
        },
        # Brand Conguration: Exposed as inverter.brand_config and can be over-written using arguments
        # from the config.yaml file but not rquired outside of this module
        "brand_config": {
            "battery_voltage": "sensor.{device_name}_battery_voltage",
            "id_timed_charge_on": "switch.{device_name}_timed_charge_slot_1_enable",
            "id_timed_charge_start_hours": "number.{device_name}_timed_charge_start_hours",
            "id_timed_charge_start_minutes": "number.{device_name}_timed_charge_start_minutes",
            "id_timed_charge_end_hours": "number.{device_name}_timed_charge_end_hours",
            "id_timed_charge_end_minutes": "number.{device_name}_timed_charge_end_minutes",
            "id_timed_charge_current": "number.{device_name}_timed_charge_current",
            "id_timed_charge_soc": "number.{device_name}_timed_charge_soc",
            "id_timed_discharge_on": "switch.{device_name}_timed_discharge_slot_1_enable",
            "id_timed_discharge_start_hours": "number.{device_name}_timed_discharge_start_hours",
            "id_timed_discharge_start_minutes": "number.{device_name}_timed_discharge_start_minutes",
            "id_timed_discharge_end_hours": "number.{device_name}_timed_discharge_end_hours",
            "id_timed_discharge_end_minutes": "number.{device_name}_timed_discharge_end_minutes",
            "id_timed_discharge_current": "number.{device_name}_timed_discharge_current",
            "id_timed_discharge_soc": "number.{device_name}_timed_discharge_soc",
            "id_timed_charge_button": "button.{device_name}_update_charge_times",
            "id_timed_discharge_button": "button.{device_name}_update_discharge_times",
            "id_timed_charge_discharge_button": "button.{device_name}_update_charge_discharge_times",
            "id_inverter_mode": "select.{device_name}_energy_storage_control_switch",
            "id_backup_mode_soc": "number.{device_name}_backup_mode_soc",
            "id_solar_power": ["sensor.{device_name}_pv_power_1", "sensor.{device_name}_pv_power_2"],
        },
    },
    "SOLIS_CORE_MODBUS": {
        "online": "sensor.{device_name}_overdischarge_soc",
        "codes": SOLIS_DEFAULT_CODES,
        "default_config": {
            "maximum_dod_percent": "sensor.{device_name}_overdischarge_soc",
            "id_battery_soc": "sensor.{device_name}_battery_soc",
            "id_consumption_today": "sensor.{device_name}_daily_consumption",
            "id_grid_import_today": "sensor.{device_name}_daily_energy_imported",
            "id_grid_export_today": "sensor.{device_name}_daily_energy_exported",
            "id_grid_power": "sensor.{device_name}_grid_active_power",
            "id_inverter_ac_power": "sensor.{device_name}_inverter_ac_power",
            "supports_hold_soc": True,
            "supports_forced_discharge": True,
            "update_cycle_seconds": 60,
        },
        "brand_config": {
            "modbus_hub": "solis",
            "modbus_slave": 1,
            "battery_voltage": "sensor.{device_name}_battery_voltage",
            "id_timed_charge_start_hours": "sensor.{device_name}_timed_charge_start_hour",
            "id_timed_charge_start_minutes": "sensor.{device_name}_timed_charge_start_minute",
            "id_timed_charge_end_hours": "sensor.{device_name}_timed_charge_end_hour",
            "id_timed_charge_end_minutes": "sensor.{device_name}_timed_charge_end_minute",
            "id_timed_charge_current": "sensor.{device_name}_timed_charge_current_limit",
            "id_timed_discharge_start_hours": "sensor.{device_name}_timed_discharge_start_hour",
            "id_timed_discharge_start_minutes": "sensor.{device_name}_timed_discharge_start_minute",
            "id_timed_discharge_end_hours": "sensor.{device_name}_timed_discharge_end_hour",
            "id_timed_discharge_end_minutes": "sensor.{device_name}_timed_discharge_end_minute",
            "id_timed_discharge_current": "sensor.{device_name}_timed_discharge_current_limit",
            "id_inverter_mode": "sensor.{device_name}_energy_storage_control_switch",
            "id_backup_mode_soc": "sensor.{device_name}_backup_mode_soc",
        },
    },
    "SOLIS_SOLARMAN": {
        "codes": {
            True: SOLIS_DEFAULT_CODES[True],
            False: {
                "Self Use": 33,
                "Optimized Revenue": 34,
                "Time of Use": 35,
                "Off-Grid Storage": 36,
                "Battery Wake-Up": 40,
                "Backup/Reserve": 40,
                "Feed-In Priority": 96,
            },
        },
        "default_config": {
            "maximum_dod_percent": 15,
            "id_battery_soc": "sensor.{device_name}_battery_soc",
            "id_consumption_today": "sensor.{device_name}_daily_house_backup_consumption",
            "id_grid_power": "sensor.{device_name}_meter_active_power",
            "id_grid_import_today": "sensor.{device_name}_daily_energy_imported",
            "id_inverter_ac_power": "sensor.{device_name}_inverter_ac_power",
            "supports_hold_soc": True,
            "supports_forced_discharge": True,
            "update_cycle_seconds": 60,
        },
        "brand_config": {
            "battery_voltage": "sensor.{device_name}_battery_voltage",
            "id_timed_charge_start_hours": "sensor.{device_name}_timed_charge_start_hour",
            "id_timed_charge_start_minutes": "sensor.{device_name}_timed_charge_start_minute",
            "id_timed_charge_end_hours": "sensor.{device_name}_timed_charge_end_hour",
            "id_timed_charge_end_minutes": "sensor.{device_name}_timed_charge_end_minute",
            "id_timed_charge_current": "sensor.{device_name}_timed_charge_current_limit",
            "id_timed_discharge_start_hours": "sensor.{device_name}_timed_discharge_start_hour",
            "id_timed_discharge_start_minutes": "sensor.{device_name}_timed_discharge_start_minute",
            "id_timed_discharge_end_hours": "sensor.{device_name}_timed_discharge_end_hour",
            "id_timed_discharge_end_minutes": "sensor.{device_name}_timed_discharge_end_minute",
            "id_timed_discharge_current": "sensor.{device_name}_timed_discharge_current_limit",
            "id_inverter_mode": "sensor.{device_name}_storage_control_mode",
            "id_backup_mode_soc": "sensor.{device_name}_backup_mode_soc",
        },
    },
    "SOLIS_SOLARMAN_V2": {
        "online": "sensor.{device_name}_overdischarge_soc",
        "codes": {
            True: SOLIS_DEFAULT_CODES[True],
            False: {
                "Self Use": 33,
                "Optimized Revenue": 34,
                "Time of Use": 35,
                "Off-Grid Storage": 36,
                "Battery Wake-Up": 40,
                "Backup/Reserve": 40,
                "Feed-In Priority": 96,
            },
        },
        "default_config": {
            "maximum_dod_percent": "sensor.{device_name}_overdischarge_soc",
            "id_battery_soc": "sensor.{device_name}_battery",
            "id_consumption_today": "sensor.{device_name}_today_load_consumption",
            "id_grid_power": "sensor.{device_name}_meter_active_power",
            "id_grid_import_today": "sensor.{device_name}_today_energy_import",
            "id_grid_export_today": "sensor.{device_name}_today_energy_export",
            "id_inverter_ac_power": "sensor.{device_name}_inverter_ac_power",
            "supports_hold_soc": True,
            "supports_forced_discharge": True,
            "update_cycle_seconds": 60,
        },
        "brand_config": {
            "battery_voltage": "sensor.{device_name}_battery_voltage",
            "id_timed_charge_start": "time.{device_name}_timed_charge_start",
            "id_timed_charge_end": "time.{device_name}_timed_charge_end",
            "id_timed_charge_current": "number.{device_name}_timed_charge_current",
            "id_timed_discharge_start": "time.{device_name}_timed_discharge_start",
            "id_timed_discharge_end": "time.{device_name}_timed_discharge_end",
            "id_timed_discharge_current": "number.{device_name}_timed_discharge_current",
            "id_inverter_mode": "select.{device_name}_storage_control_mode",
            "id_backup_mode_soc": "sensor.{device_name}_backup_mode_soc",
        },
    },
    "SOLIS_CLOUD": {
        "online": "sensor.{device_name}_state",
        "codes": SOLIS_DEFAULT_CODES,
        "default_config": {
            "maximum_dod_percent": "sensor.{device_name}_force_discharge_soc",
            "id_consumption_today": "sensor.{device_name}_daily_grid_energy_used",
            "id_grid_import_today": "sensor.{device_name}_daily_grid_energy_purchased",
            "id_grid_export_today": "sensor.{device_name}_daily_on_grid_energy",
            "id_battery_soc": "sensor.{device_name}_remaining_battery_capacity",
            "supports_hold_soc": True,
            "supports_forced_discharge": True,
            "update_cycle_seconds": 0,
        },
        "brand_config": {
            "battery_voltage": "sensor.{device_name}_battery_voltage",
            "id_inverter_mode": "select.{device_name}_energy_storage_control_switch",
            "id_timed_charge_start": "time.{device_name}_timed_charge_start_1",
            "id_timed_charge_end": "time.{device_name}_timed_charge_end_1",
            "id_timed_charge_current": "number.{device_name}_timed_charge_current_1",
            "id_timed_charge_soc": "number.{device_name}_timed_charge_soc_1",
            "id_timed_discharge_start": "time.{device_name}_timed_discharge_start_1",
            "id_timed_discharge_end": "time.{device_name}_timed_discharge_end_1",
            "id_timed_discharge_current": "number.{device_name}_timed_discharge_current_1",
            "id_timed_discharge_soc": "number.{device_name}_timed_discharge_soc_1",
            "id_timed_charge_button": "button.{device_name}_update_timed_charge_1",
            "id_timed_discharge_button": "button.{device_name}_update_timed_discharge_1",
            "id_timed_charge_discharge_button": "button.{device_name}_update_timed_charge_discharge_1",
        },
    },
}


def create_inverter_controller(inverter_type: str, host):
    if inverter_type == "SOLIS_CORE_MODBUS":
        return SolisCoreModbusInverter(
            inverter_type=inverter_type,
            host=host,
        )

    elif inverter_type == "SOLIS_CLOUD":
        return SolisCloudInverter(
            inverter_type=inverter_type,
            host=host,
        )

    elif inverter_type == "SOLIS_SOLAX_MODBUS":
        return SolisSolaxModbusInverter(
            inverter_type=inverter_type,
            host=host,
        )

    elif inverter_type == "SOLIS_SOLARMAN":
        return SolisSolarmanModbusInverter(
            inverter_type=inverter_type,
            host=host,
        )

    elif inverter_type == "SOLIS_SOLARMAN_V2":
        return SolisSolarmanV2Inverter(
            inverter_type=inverter_type,
            host=host,
        )

    else:
        host.log(f"Unknown inverter type {inverter_type}")
        return False


# This is the Base Class
class BaseInverterController(ABC):
    def __init__(self, inverter_type: str, host) -> None:
        self._host = host
        self._tz = self._host.tz
        if host is not None:
            self.log = host.log
        self._type = inverter_type
        self._device_name = self._host.device_name
        self._config = {}
        self._brand_config = {}
        self._online = INVERTER_DEFS[self._type]["online"].replace("{device_name}", self._device_name)
        for defs, conf in zip(
            [INVERTER_DEFS[self._type][x] for x in ["default_config", "brand_config"]],
            [self._config, self._brand_config],
        ):
            for item in defs:
                if isinstance(defs[item], str):
                    conf[item] = defs[item].replace("{device_name}", self._device_name)
                elif isinstance(defs[item], list):
                    conf[item] = [z.replace("{device_name}", self._device_name) for z in defs[item]]
                else:
                    conf[item] = defs[item]
        self.log(f"Loading controller for inverter type {self._type}")

    @property
    @abstractmethod
    def is_online(self):
        pass

    @property
    @abstractmethod
    def timed_mode(self):
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
    def hold_soc(self, enable, target_soc=None, **kwargs):
        pass

    def get_config(self, config_variable, default=None):
        return self._host.get_config(config_variable, default)

    @property
    @abstractmethod
    def status(self):
        pass

    @property
    def config(self):
        return self._config

    @property
    def brand_config(self):
        return self._brand_config

    def write_to_hass(self, entity_id, value, **kwargs):
        try:
            value = float(value)
        except:
            pass

        if isinstance(value, int) or isinstance(value, float):
            return self._host.write_and_poll_value(entity_id=entity_id, value=value, **kwargs)
        else:
            # self.log("write_to_hass - time detected")
            # var_type = type(value)
            # self.log(f"value = {value}")
            # self.log(f"type of value = {var_type}")
            try:
                return self._host.write_and_poll_time(entity_id=entity_id, time=value, verbose=True)
            except:
                self.log(
                    f"Unable to write value {value} to entity {entity_id}",
                    level="ERROR",
                )
                return True, False

    def _press_button(self, entity_id):
        self._host.call_service("button/press", entity_id=entity_id)
        time.sleep(0.5)
        try:
            time_pressed = pd.Timestamp(self._host.get_state_retry(entity_id))
            dt = (pd.Timestamp.now(self._tz) - time_pressed).total_seconds()
            if dt < 10:
                self.log(f"Successfully pressed button {entity_id}")
            else:
                self.log(
                    f"Failed to press button {entity_id}. Last pressed at {time_pressed.strftime(TIMEFORMAT)} ({dt:0.2f} seconds ago)"
                )
        except:
            self.log(f"Failed to press button {entity_id}: it appears to never have been pressed.")


class SolisInverter(BaseInverterController):
    def __init__(self, inverter_type, host):
        super().__init__(inverter_type, host)
        self._hmi_fb00 = host.args.get("hmi_firmware_fb00_plus", False)
        self.log(f"HMI Firmware Flag set to {self._hmi_fb00}")
        self._codes = INVERTER_DEFS[inverter_type]["codes"][self._hmi_fb00]
        self._modes = {self._codes[code]: code for code in self._codes}
        self._bits = SOLIS_BITS
        self._requires_button_press = True
        self._hold_soc = {"active": False, "soc": 0}

    @property
    def timed_mode(self):
        if self._hmi_fb00:
            timed_mode = (
                self._get_slot_status(direction="charge")
                and self._get_slot_status(direction="discharge")
                and int(self._get_energy_control_code()) == 33
            )
            return timed_mode
        else:
            return int(self._get_energy_control_code()) == 35

    def _get_slot_status(self, direction="charge"):
        cfg = f"id_timed_{direction}_on"
        if cfg in self._brand_config:
            return self.get_config(cfg)
        else:
            self.log(f"{cfg} is not defined so assuming switch is on", level="WARNING")
            return True

    @final
    def enable_timed_mode(self):
        # set the energy control switch depending on HMI version
        if self._hmi_fb00:
            code = 33
            self._enable_slot(direction="charge")
            self._enable_slot(direction="discharge")
        else:
            code = 35
        self._set_energy_control_switch(code)

    def _enable_slot(self, direction="charge"):
        cfg = f"id_timed_{direction}_on"
        entity_id = self._brand_config.get(cfg, None)
        if cfg in self._brand_config and entity_id is not None:
            try:
                self._host.call_service("switch/turn_on", entity_id=entity_id)
            except:
                self.log(f"Failed to turn on switch {entity_id}", level="WARNING")
        else:
            self.log(f"{cfg} is not defined so assuming switch is on", level="WARNING")
            return True

    def _set_energy_control_switch(self, code: int):
        mode = self._modes.get(code, None)
        if mode is not None:
            self._host.set_select("inverter_mode", mode)
        else:
            self.logf("Unable to get mode for control switch code {code}")

    @property
    @final
    def status(self):
        time_now = pd.Timestamp.now(tz=self._tz)
        code = self._get_energy_control_code()
        status = {"code": code}
        status = status | {"switches": self._switches(code)}
        status = status | {direction: self._get_times_current(direction=direction) for direction in DIRECTIONS}
        voltage = self.voltage
        for direction in DIRECTIONS:
            status[direction]["power"] = status[direction]["current"] * voltage
            status[direction]["active"] = (
                time_now >= status[direction]["start"]
                and time_now < status[direction]["end"]
                and status[direction].get("current", 0)
                >= 0  # SVB changed to ">=" so IOG slots are seen as charging (as they effectively use timed charge
                and (self._hmi_fb00 or status["switches"].get("Timed", False))
                and status["switches"].get("GridCharge", False)
            )
        status["hold_soc"] = self._hold_soc

        return status

    def _switches(self, code):
        return {bit: (code & 2**i == 2**i) for i, bit in enumerate(self._bits)}

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

    def _get_energy_control_code(self):
        mode = self.get_config("id_inverter_mode")
        code = self._codes.get(mode, None)
        if code is None:
            self.log(f"Unable to get code for energy control mode {mode}")
        return code

    def control_charge(self, enable, **kwargs):
        self._control_charge_discharge("charge", enable, **kwargs)

    def control_discharge(self, enable, **kwargs):
        self._control_charge_discharge("discharge", enable, **kwargs)

    def _control_charge_discharge(self, direction, enable, **kwargs):
        times = {}
        if enable:
            times["start"] = kwargs.get("start", None)
            times["end"] = kwargs.get("end", None)
            current = kwargs.get("current", abs(round(kwargs.get("power", 0) / self.voltage, 1)))
            target_soc = kwargs.get("target_soc", None)

        else:
            # Disable by setting end time = start time:
            times["start"] = self.status["charge"]["start"]
            times["end"] = times["start"]
            current = 0
            target_soc = None

        if target_soc is None and self._hmi_fb00:
            if direction == "charge":
                target_soc = 100
            else:
                target_soc = self.get_config("maximum_dod_percent")

        battery_current_limit = self.get_config("battery_current_limit_amps")
        if battery_current_limit < current:
            self.log(
                f"battery_current_limit_amps of {battery_current_limit} is less than current of {current}A required by charging plan."
            )
            self.log(f"Reducing inverter charge current to {battery_current_limit}A. ")
            self.log("Check value of charger_power_watts in config.yaml if this is unexpected.")
            self.log("")

        current = min(current, battery_current_limit)

        changed = self._set_times(direction, **times)
        changed = changed or self._set_current(direction, current)

        if changed and self._requires_button_press:
            self.log("Something changed - need to press the appropriate Button")
            if self._hmi_fb00:
                entity_id = self.brand_config.get(f"id_timed_{direction}_button", None)
            else:
                entity_id = self.brand_config.get(f"id_timed_charge_discharge_button", None)

            if entity_id is not None:
                self._press_button(entity_id=entity_id)

        if self._hmi_fb00:
            """
            There seems to be a bug where with the FB00+ firmware the changes aren't saved unless
            the target SOC is also set
            """
            if changed or (self.status[direction].get("soc", 0) != target_soc):
                self._set_target_soc(direction, target_soc, forced=True)

    def hold_soc(self, enable, target_soc=0, **kwargs):
        start = kwargs.get("start", pd.Timestamp.now(tz=self._tz).floor("1min"))
        end = kwargs.get("end", pd.Timestamp.now(tz=self._tz).ceil("30min"))
        self._hold_soc = {"active": enable, "soc": target_soc}

        if self._hmi_fb00:
            self._control_charge_discharge(
                "charge",
                enable=enable,
                start=start,
                end=end,
                power=3000,
                target_soc=target_soc,
            )
        else:

            self._control_charge_discharge(
                "charge",
                enable=enable,
                start=start,
                end=end,
                power=0,
            )

    def _get_times_current(self, direction):
        times = {
            limit: pd.Timestamp(self.get_config(f"id_timed_{direction}_{limit}", "0:00"), tz=self._tz)
            for limit in LIMITS
        }
        current = {"current": self.get_config(f"id_timed_{direction}_current", 0)}
        if self._hmi_fb00:
            target_soc = {"target_soc": self.get_config(f"id_timed_{direction}_soc", 0)}
        else:
            target_soc = {}
        return times | current | target_soc

    def _set_times(self, direction, **times) -> bool:
        value_changed = False
        # Solis inverters can't cope with time slots spanning midnight so if the end is a different day
        # crop it to 23:59

        if times["end"] is not None:
            if times["start"] is None:
                start_day = pd.Timestamp.now().day
            else:
                start_day = times["start"].day

            # if times["end"].day != times["start"].day:
            if start_day != times["end"].day:
                times["end"] = times["end"].floor("1D") - pd.Timedelta("1min")

        for limit in LIMITS:
            time = times.get(limit, None)
            if time is not None:
                entity_id = self._host.config.get(f"id_timed_{direction}_{limit}", None)
                if entity_id is not None:
                    changed, written = self.write_to_hass(entity_id=entity_id, value=time, verbose=True)
                    value_changed = value_changed or written

        return value_changed

    def _set_current(self, direction, current: float = 0) -> bool:
        entity_id = self._host.config.get(f"id_timed_{direction}_current", None)
        if entity_id is not None:
            changed, written = self.write_to_hass(entity_id=entity_id, value=current, tolerance=0.1, verbose=True)

        if changed:
            if written:
                self.log(f"Current {current}A written to inverter")
            else:
                self.log(f"Failed to write {current} to inverter")
        else:
            self.log("Inverter already at correct current")

        return not (changed and not written)

    def _set_target_soc(self, direction, target_soc: int = 100, forced=True) -> bool:
        entity_id = self._host.config.get(f"id_timed_{direction}_soc", None)
        if forced:
            tolerance = -1
        else:
            tolerance = 0

        if entity_id is not None:
            changed, written = self.write_to_hass(entity_id=entity_id, value=target_soc, tolerance=tolerance)

        if changed:
            if written:
                self.log(f"Target SOC {target_soc}% written to inverter")
            else:
                self.log(f"Failed to write SOC {target_soc}% to inverter")
        else:
            self.log("Inverter already at correct target SOC")

        return not (changed and not written)

    @property
    def voltage(self):
        return self.get_config("battery_voltage", 50)


class SolisCloudInverter(SolisInverter):
    def __init__(self, inverter_type: str, host):
        super().__init__(inverter_type, host)


class SolisSolarmanV2Inverter(SolisInverter):
    def __init__(self, inverter_type, host):
        super().__init__(inverter_type, host)
        self._requires_button_press = False

    def _set_current(self, direction, current: float = 0) -> bool:
        entity_id = self._host.config.get(f"id_timed_{direction}_current", None)

        current = round(current, 1)

        if entity_id is not None:
            changed, written = self.write_to_hass(entity_id=entity_id, value=current, tolerance=0.1, verbose=True)

        if changed:
            if written:
                self.log(f"Current {current}A written to inverter")
            else:
                self.log(f"Failed to write {current} to inverter")
        else:
            self.log("Inverter already at correct current")

        return not (changed and not written)


class SolisSolaxModbusInverter(SolisInverter):
    def __init__(self, inverter_type: str, host):
        super().__init__(inverter_type, host)
        entity_id = self.brand_config["id_inverter_mode"]
        entity_modes = self._host.get_state_retry(entity_id, attribute="options")
        self._codes = INVERTER_DEFS[inverter_type]["codes"][self._hmi_fb00]
        self._modes = {self._codes[code]: code for code in entity_modes}

    def _get_times_current(self, direction):
        # Required if the times are set as separate_hours and units
        times = {}
        for limit in LIMITS:
            x = {unit: self.get_config(f"id_timed_{direction}_{limit}_{unit}", 0) for unit in TIME_UNITS}
            times[limit] = pd.Timestamp(pd.Timestamp.today().date(), tz=self._tz) + pd.Timedelta(**x)

        current = {"current": self.get_config(f"id_timed_{direction}_current", 0)}
        if self._hmi_fb00:
            target_soc = {"target_soc": self.get_config(f"id_timed_{direction}_soc", 0)}
        else:
            target_soc = {}
        return times | current | target_soc

    def _set_times(self, direction, **times) -> bool:
        # Required if the times are set as separate_hours and units
        value_changed = False

        # Solis inverters can't cope with time slots spanning midnight so if the end is a different day
        # crop it to 23:59

        if times["end"] is not None:
            if times["start"] is None:
                start_day = pd.Timestamp.now().day
            else:
                start_day = times["start"].day

            # if times["end"].day != times["start"].day:
            if start_day != times["end"].day:
                times["end"] = times["end"].floor("1D") - pd.Timedelta("1min")

        for limit in LIMITS:
            time = times.get(limit, None)
            if time is not None:
                entity_id = self._host.config.get(f"id_timed_{direction}_{limit}_hours", None)
                if entity_id is not None:
                    changed, written = self.write_to_hass(entity_id=entity_id, value=time.hour, verbose=True)
                    value_changed = value_changed or (changed and written)
                entity_id = self._host.config.get(f"id_timed_{direction}_{limit}_minutes", None)
                if entity_id is not None:
                    changed, written = self.write_to_hass(entity_id=entity_id, value=time.minute, verbose=True)
                    value_changed = value_changed or (changed and written)
        return value_changed


class SolisCoreModbusInverter(SolisInverter):
    def __init__(self, inverter_type, host):
        super().__init__(inverter_type, host)
        self._requires_button_press = False
        self._registers = REGISTERS[self._hmi_fb00]
        self._hub = self.get_config("modbus_hub")
        self._slave = self.get_config("modbus_slave")

    def _get_energy_control_code(self):
        code = int(self.get_config("id_inverter_mode"))
        return code

    def _set_energy_control_switch(self, code: int):
        cfg = "id_inverter_mode"
        return self._write_modbus_register(
            register=self._registers["storage_control_switch"],
            value=int(code),
            cfg=cfg,
        )

    def write_time_register(self, direction, limit, unit, value):
        cfg = f"id_timed_{direction}_{limit}_{unit}"
        register = self._registers[f"timed_{direction}_{limit}_{unit}"]
        return self._write_modbus_register(
            register=register,
            value=int(value),
            cfg=cfg,
        )

    def write_current_register(self, direction, current, tolerance):
        cfg = f"id_timed_{direction}_current"
        register = self._registers[f"timed_{direction}_current"]
        return self._write_modbus_register(
            register=register,
            value=round(current, 1),
            cfg=cfg,
            tolerance=tolerance,
            multiplier=10,
        )

    def write_soc_register(self, direction, target_soc):
        cfg = "id_timed_{direction}_soc"
        register = self._registers[f"timed_{direction}_soc"]
        return self._write_modbus_register(register=register, value=int(target_soc), cfg=cfg)

    def _write_modbus_register(self, register, value, cfg=None, tolerance=0, multiplier=1):
        changed = True
        written = False
        self.log(f"Setting register {register} to {value} for entity {cfg}")
        if cfg is not None:
            current_value = int(float(self.get_config(cfg)))
            if isinstance(current_value, int) and abs(current_value / multiplier - value) <= tolerance:
                self.log(f"Inverter value already set to {value}.")
                changed = False

            if changed:
                data = {
                    "address": register,
                    "slave": self._slave,
                    "value": int(round(value * multiplier, 0)),
                    "hub": self._hub,
                }
                self._host.call_service("modbus/write_register", **data)
                sleep(0.1)
                new_value = int(float(self.get_config(cfg))) / multiplier

                written = new_value == value
        return changed, written

    def _get_times_current(self, direction):
        # Required if the times are set as separate_hours and units
        times = {}
        for limit in LIMITS:
            x = {unit: self.get_config(f"id_timed_{direction}_{limit}_{unit}", 0) for unit in TIME_UNITS}
            times[limit] = pd.Timestamp(pd.Timestamp.today().date(), tz=self._tz) + pd.Timedelta(**x)

        current = {"current": self.get_config(f"id_timed_{direction}_current", 0)}
        if self._hmi_fb00:
            target_soc = {"target_soc": self.get_config(f"id_timed_{direction}_soc", 0)}
        else:
            target_soc = {}
        return times | current | target_soc

    def _set_times(self, direction, **times) -> bool:
        # Required if the times are set as separate_hours and units
        value_changed = False
        for limit in LIMITS:
            time = times.get(limit, None)
            if time is not None:
                changed, written = self.write_time_register(direction, limit, "hours", time.hour)
                value_changed = value_changed or (changed and written)
                changed, written = self.write_time_register(direction, limit, "minutes", time.minute)
                value_changed = value_changed or (changed and written)
        return value_changed


class SolisSolarmanModbusInverter(SolisInverter):
    def __init__(self, inverter_type, host):
        super().__init__(inverter_type, host)
        self._requires_button_press = False

    def _set_energy_control_switch(self, code: int):
        cfg = "id_inverter_mode"
        return self._write_modbus_register(
            register=self._registers["storage_control_switch"],
            value=int(code),
            cfg=cfg,
        )

    def _write_modbus_register(self, register, value, cfg=None, tolerance=0, multiplier=1):
        if cfg is not None and self._host.entity_exists(cfg):
            old_value = int(float(self._host.get_state_retry(entity_id=cfg)))
            if isinstance(old_value, int) and abs(old_value - value) <= tolerance:
                self.log(f"Inverter value already set to {value}.")
                changed = False

        if changed:
            data = {"register": register, "value": value}
            self._host.call_service("solarman/write_holding_register", **data)
            written = True
