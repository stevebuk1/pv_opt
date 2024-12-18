import pandas as pd
import time
import json

TIMEFORMAT = "%H:%M"
INVERTER_DEFS = {
    "SUNSYNK_SOLARSYNK2": {
        "online": "sensor.{device_name}_{inverter_sn}_battery_soc",
        # "modes": {
        #     1: "Selfuse - No Grid Charging",
        #     3: "Timed Charge/Discharge - No Grid Charging",
        #     17: "Backup/Reserve - No Grid Charging",
        #     33: "Selfuse",
        #     35: "Timed Charge/Discharge",
        #     37: "Off-Grid Mode",
        #     41: "Battery Awaken",
        #     43: "Battery Awaken + Timed Charge/Discharge",
        #     49: "Backup/Reserve - No Timed Charge/Discharge",
        #     51: "Backup/Reserve",
        # },
        # "bits": [
        #     "SelfUse",
        #     "Timed",
        #     "OffGrid",
        #     "BatteryWake",
        #     "Backup",
        #     "GridCharge",
        #     "FeedInPriority",
        # ],
        # Default Configuration: Exposed as inverter.config and provides defaults for this inverter for the
        # required config. These config items can be over-written by config specified in the config.yaml
        # file. They are required for the main PV_Opt module and if they cannot be found an ERROR will be
        # raised
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
            "id_timed_charge_unused": ["sensor.{device_name}_{inverter_sn}_" + f"prog{i}_time" for i in range(2, 7)],
            "id_timed_charge_enable": "sensor.{device_name}_{inverter_sn}_prog1_charge",
            "id_timed_charge_capacity": "sensor.{device_name}_{inverter_sn}_prog1_capacity",
            "id_timed_discharge_start": "sensor.{device_name}_{inverter_sn}_prog3_time",
            "id_timed_discharge_end": "sensor.{device_name}_{inverter_sn}_prog4_time",
            "id_timed_discharge_unused": [
                "sensor.{device_name}_{inverter_sn}_" + f"prog{i}_time" for i in [1, 2, 5, 6]
            ],
            "id_timed_dicharge_enable": "sensor.{device_name}_{inverter_sn}_prog3_charge",
            "id_timed_discharge_capacity": "sensor.{device_name}_{inverter_sn}_prog3_capacity",
            "json_work_mode": "sysWorkMode",
            "json_priority_load": "energyMode",
            "json_grid_charge": "sdChargeOn",
            "json_use_timer": "peakAndVallery",
            "json_timed_charge_start": "sellTime1",
            "json_timed_charge_end": "sellTime2",
            "json_timed_charge_unused": [f"sellTime{i}" for i in range(2, 7)],
            "json_timed_charge_enable": "time1on",
            "json_timed_charge_target_soc": "cap1",
            "json_charge_current": "sdBatteryCurrent",
            "json_gen_charge_enable": "genTime1on",
            "json_timed_discharge_start": "sellTime3",
            "json_timed_discharge_end": "sellTime4",
            "json_timed_discharge_unused": [f"sellTime{i}" for i in [1, 2, 5, 6]],
            "json_timed_discharge_enable": "time3on",
            "json_timed_discharge_target_soc": "cap3",
            "json_timed_discharge_power": "sellTime3Pac",
            "json_gen_discharge_enable": "genTime3on",
        },
    },
}


class InverterController:
    def __init__(self, inverter_type, host) -> None:
        self.host = host
        self.tz = self.host.tz
        if host is not None:
            self.log = host.log
            self.tz = self.host.tz
            self.config = self.host.config

        self.type = inverter_type

        self.brand_config = {}
        for defs, conf in zip(
            [INVERTER_DEFS[self.type][x] for x in ["default_config", "brand_config"]],
            [self.config, self.brand_config],
        ):
            for item in defs:
                if isinstance(defs[item], str):
                    conf[item] = defs[item].replace("{device_name}", self.host.device_name)
                    conf[item] = defs[item].replace("{inverter_sn}", self.host.inverter_sn)
                elif isinstance(defs[item], list):
                    conf[item] = [z.replace("{device_name}", self.host.device_name) for z in defs[item]]
                    conf[item] = [z.replace("{inverter_sn}", self.host.inverter_sn) for z in defs[item]]
                else:
                    conf[item] = defs[item]

    @property
    def is_online(self):
        entity_id = INVERTER_DEFS[self.type].get("online", (None, None))
        if entity_id is not None:
            entity_id = entity_id.replace("{device_name}", self.host.device_name)
            return self.host.get_state(entity_id) not in ["unknown", "unavailable"]
        else:
            return True

    def _unknown_inverter(self):
        e = f"Unknown inverter type {self.type}"
        self.log(e, level="ERROR")
        self.host.status(e)
        raise Exception(e)

    def _solarsynk_set_helper(self, **kwargs):
        current_json = json.loads(self.host.get_config("id_control_helper"))
        new_json = json.dumps(current_json | kwargs)
        entity_id = self.host.config("id_control_helper")
        self.rlog(f"Setting SolarSynk input helper {entity_id} to {new_json}")
        #  self.host.set_state(entity_id=entity_id, state=new_json)

    def enable_timed_mode(self):
        if self.type == "SUNSYNK_SOLARSYNK2":
            params = {
                self.config["json_use_timer"]: 1,
                self.config["json_priority_load"]: 1,
            }
            self._solarsynk_set_helper(params)

        else:
            self._unknown_inverter()

    def control_charge(self, enable, **kwargs):
        if self.type == "SUNSYNK_SOLARSYNK2":
            time_now = pd.Timestamp.now(tz=self.tz)

            if enable:
                self.enable_timed_mode()
                params = {
                    self.config["json_work_mode"]: 2,
                    self.config["json_timed_charge_target_soc"]: kwargs.get("target_soc", 100),
                    self.config["json_timed_charge_start"]: kwargs.get("start", time_now.strftime(TIMEFORMAT)),
                    self.config["json_timed_charge_end"]: kwargs.get(
                        "end", time_now.ceil("30min").strftime(TIMEFORMAT)
                    ),
                    self.config["json_charge_current"]: min(
                        kwargs.get("power", 0) / self.host.get_config("battery_voltage"),
                        self.host.get_config("battery_current_limit_amps"),
                    ),
                    self.config["json_timed_charge_enable"]: True,
                    self.config["json_gen_charge_enable"]: False,
                } | {x: "00:00" for x in self.config["json_timed_charge_unused"]}

                self._solarsynk_set_helper(params)

            else:
                params = {
                    self.config["json_work_mode"]: 2,
                    self.config["json_target_soc"]: 100,
                    self.config["json_timed_charge_start"]: "00:00",
                    self.config["json_timed_charge_end"]: "00:00",
                    self.config["json_charge_current"]: self.host.get_config("battery_current_limit_amps"),
                    self.config["json_timed_charge_enable"]: False,
                    self.config["json_gen_charge_enable"]: True,
                } | {x: "00:00" for x in self.config["json_timed_charge_unused"]}
        else:
            self._unknown_inverter()

    def control_discharge(self, enable, **kwargs):
        if self.type == "SUNSYNK_SOLARSYNK2":
            time_now = pd.Timestamp.now(tz=self.tz)

            if enable:
                self.enable_timed_mode()
                params = {
                    self.config["json_work_mode"]: 0,
                    self.config["json_timed_discharge_target_soc"]: kwargs.get(
                        "target_soc", self.host.get_config("maximum_dod_percent")
                    ),
                    self.config["json_timed_discharge_start"]: kwargs.get("start", time_now.strftime(TIMEFORMAT)),
                    self.config["json_timed_discharge_end"]: kwargs.get(
                        "end", time_now.ceil("30min").strftime(TIMEFORMAT)
                    ),
                    self.config["json_discharge_power"]: kwargs.get("power", 0),
                    self.config["json_timed_discharge_enable"]: True,
                    self.config["json_gen_discharge_enable"]: False,
                } | {x: "00:00" for x in self.config["json_timed_discharge_unused"]}

                self._solarsynk_set_helper(**params)

            else:
                params = {
                    self.config["json_work_mode"]: 2,
                    self.config["json_timed_discharge_target_soc"]: 100,
                    self.config["json_timed_discharge_start"]: "00:00",
                    self.config["json_timed_discharge_end"]: "00:00",
                    self.config["json_discharge_power"]: 0,
                    self.config["json_timed_discharge_enable"]: False,
                    self.config["json_gen_discharge_enable"]: True,
                } | {x: "00:00" for x in self.config["json_timed_discharge_unused"]}
        else:
            self._unknown_inverter()

    def hold_soc(self, enable, soc=None):
        if self.type == "SUNSYNK_SOLARSYNK2":
            pass

        else:
            self._unknown_inverter()

    @property
    def status(self):
        status = None
        time_now = pd.Timestamp.now(tz=self.tz)

        if self.type == "SUNSYNK_SOLARSYNK2":
            charge_start = pd.Timestamp(self.host.get_config("id_timed_charge_start"), tz=self.tz)
            charge_end = pd.Timestamp(self.host.get_config("id_timed_charge_end"), tz=self.tz)
            discharge_start = pd.Timestamp(self.host.get_config("id_timed_charge_start"), tz=self.tz)
            discharge_end = pd.Timestamp(self.host.get_config("id_timed_charge_end"), tz=self.tz)

            status = {
                "timer mode": self.host.get_config("id_use_timer"),
                "priority load": self.host.get_config("id_priority_load"),
                "charge": {
                    "start": charge_start,
                    "end": charge_end,
                    "active": self.host.get_config("id_timed_charge_enable")
                    and (time_now >= charge_start)
                    and (time_now < charge_end),
                    "target_soc": self.host.get_config("id_timed_charge_target_soc"),
                },
                "discharge": {
                    "start": discharge_start,
                    "end": discharge_end,
                    "active": self.host.get_config("id_timed_discharge_enable")
                    and (time_now >= discharge_start)
                    and (time_now < discharge_end),
                    "target_soc": self.host.get_config("id_timed_discharge_target_soc"),
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
