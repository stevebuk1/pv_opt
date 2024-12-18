import pandas as pd
import time
import datetime as dt

import hashlib
import hmac
import base64
import json
import re
import requests
from http import HTTPStatus
from datetime import datetime, timezone

URLS = {
    "root": "https://www.soliscloud.com:13333",
    "login": "/v2/api/login",
    "control": "/v2/api/control",
    "inverterList": "/v1/api/inverterList",
    "atRead": "/v2/api/atRead",
}

TIMEFORMAT = "%H:%M"
INVERTER_DEFS = {
    "SOLIS_SOLAX_MODBUS": {
        "online": "number.{device_name}_battery_minimum_soc",
        "codes": {
            "SelfUse - No Grid Charging": 1,
            "Self-Use - No Grid Charging": 1,
            "Timed Charge/Discharge - No Grid Charging": 3,
            "Backup/Reserve - No Grid Charging": 17,
            "SelfUse": 33,
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
        # "modes": {
        #     1: "Self-Use - No Grid Charging",
        #     3: "Timed Charge/Discharge - No Grid Charging",
        #     17: "Backup/Reserve - No Grid Charging",
        #     33: "Self-Use",
        #     35: "Timed Charge/Discharge",
        #     37: "Off-Grid Mode",
        #     41: "Battery Awaken",
        #     43: "Battery Awaken + Timed Charge/Discharge",
        #     49: "Backup/Reserve - No Timed Charge/Discharge",
        #     51: "Backup/Reserve",
        # },
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
            # "id_grid_import_power": "sensor.{device_name}_grid_import_power",
            # "id_grid_export_power": "sensor.{device_name}_grid_export_power",
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
            "id_timed_charge_start_hours": "number.{device_name}_timed_charge_start_hours",
            "id_timed_charge_start_minutes": "number.{device_name}_timed_charge_start_minutes",
            "id_timed_charge_end_hours": "number.{device_name}_timed_charge_end_hours",
            "id_timed_charge_end_minutes": "number.{device_name}_timed_charge_end_minutes",
            "id_timed_charge_current": "number.{device_name}_timed_charge_current",
            "id_timed_discharge_start_hours": "number.{device_name}_timed_discharge_start_hours",
            "id_timed_discharge_start_minutes": "number.{device_name}_timed_discharge_start_minutes",
            "id_timed_discharge_end_hours": "number.{device_name}_timed_discharge_end_hours",
            "id_timed_discharge_end_minutes": "number.{device_name}_timed_discharge_end_minutes",
            "id_timed_discharge_current": "number.{device_name}_timed_discharge_current",
            "id_timed_charge_discharge_button": "button.{device_name}_update_charge_discharge_times",
            "id_inverter_mode": "select.{device_name}_energy_storage_control_switch",
            "id_backup_mode_soc": "number.{device_name}_backup_mode_soc",
        },
    },
    "SOLIS_CORE_MODBUS": {
        "online": "sensor.{device_name}_overdischarge_soc",
        "bits": [
            "SelfUse",
            "Timed",
            "OffGrid",
            "BatteryWake",
            "Backup",
            "GridCharge",
            "FeedInPriority",
        ],
        "registers": {
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
        "default_config": {
            "maximum_dod_percent": "sensor.{device_name}_overdischarge_soc",
            "id_battery_soc": "sensor.{device_name}_battery_soc",
            "id_consumption_today": "sensor.{device_name}_daily_consumption",
            # "id_consumption": [
            #     "sensor.{device_name}_house_load_power",
            #     "sensor.{device_name}_backup_load_power",
            # ],
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
    "SOLIS_SOLARMAN": {  #For https://github.com/StephanJoubert/home_assistant_solarman
        "online": "sensor.{device_name}_overdischarge_soc",
        "modes": {
            0x21: "Self Use",
            0x22: "Optimized Revenue",
            0x23: "Time of Use",
            0x24: "Off-Grid Storage",
            0x28: "Battery Wake-Up",
            0x60: "Feed-In Priority",
        },
        "bits": [
            "SelfUse",
            "Timed",
            "OffGrid",
            "BatteryWake",
            "Backup",
            "GridCharge",
            "FeedInPriority",
        ],
        "registers": {
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
        "default_config": {
            "maximum_dod_percent": 15,
            "id_battery_soc": "sensor.{device_name}_battery_soc",
            "id_consumption_today": "sensor.{device_name}_daily_house_backup_consumption",
            # "id_consumption": [
            #     "sensor.{device_name}_house_load_power",
            #     "sensor.{device_name}_backup_load_power",
            # ],
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

    "SOLIS_SOLARMAN_V2": {     # For https://github.com/davidrapan/ha-solarman
        "online": "sensor.{device_name}_overdischarge_soc",
        "modes": {
            0x21: "Self Use",
            0x22: "Optimized Revenue",
            0x23: "Time of Use",
            0x24: "Off-Grid Storage",
            0x28: "Battery Wake-Up",
            0x31: "Backup/Reserve",
            0x60: "Feed-In Priority",
        },

        "bits": [
            "SelfUse",
            "Timed",
            "OffGrid",
            "BatteryWake",
            "Backup",
            "GridCharge",
            "FeedInPriority",
        ],

        "registers": {
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
        "default_config": {
            "maximum_dod_percent": "sensor.{device_name}_overdischarge_soc",
            "id_battery_soc": "sensor.{device_name}_battery",
            "id_consumption_today": "sensor.{device_name}_today_load_consumption",
            # "id_consumption": [
            #     "sensor.{device_name}_house_load_power",
            #     "sensor.{device_name}_backup_load_power",
            # ],
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
        "bits": [
            "SelfUse",
            "Timed",
            "OffGrid",
            "BatteryWake",
            "Backup",
            "GridCharge",
            "FeedInPriority",
        ],     
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

        },
    },
}


class SolisCloud:
    URLS = {
        "root": "https://www.soliscloud.com:13333",
        "login": "/v2/api/login",
        "control": "/v2/api/control",
        "inverterList": "/v1/api/inverterList",
        "inverterDetail": "/v1/api/inverterDetail",
        "atRead": "/v2/api/atRead",
    }

    MAX_RETRIES = 5

    def __init__(self, username, password, key_id, key_secret, plant_id, **kwargs):
        self.username = username
        self.key_id = key_id
        self.key_secret = key_secret
        self.plant_id = plant_id
        self.md5password = hashlib.md5(password.encode("utf-8")).hexdigest()
        self.token = ""
        self.log = kwargs.get("log", print)

    def get_body(self, **params):
        body = "{"
        for key in params:
            body += f'"{key}":"{params[key]}",'
        body = body[:-1] + "}"
        return body

    def digest(self, body: str) -> str:
        return base64.b64encode(hashlib.md5(body.encode("utf-8")).digest()).decode("utf-8")

    def header(self, body: str, canonicalized_resource: str) -> dict[str, str]:
        content_md5 = self.digest(body)
        content_type = "application/json"

        now = datetime.now(timezone.utc)
        date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

        encrypt_str = "POST" + "\n" + content_md5 + "\n" + content_type + "\n" + date + "\n" + canonicalized_resource
        hmac_obj = hmac.new(self.key_secret.encode("utf-8"), msg=encrypt_str.encode("utf-8"), digestmod=hashlib.sha1)
        sign = base64.b64encode(hmac_obj.digest())
        authorization = "API " + str(self.key_id) + ":" + sign.decode("utf-8")

        header = {
            "Content-MD5": content_md5,
            "Content-Type": content_type,
            "Date": date,
            "Authorization": authorization,
        }
        return header

    @property
    def inverter_id(self):
        body = self.get_body(stationId=self.plant_id)
        header = self.header(body, self.URLS["inverterList"])
        response = requests.post(self.URLS["root"] + self.URLS["inverterList"], data=body, headers=header)
        if response.status_code == HTTPStatus.OK:
            return response.json()["data"]["page"]["records"][0].get("id", "")

    @property
    def inverter_sn(self):
        body = self.get_body(stationId=self.plant_id)
        header = self.header(body, self.URLS["inverterList"])
        response = requests.post(self.URLS["root"] + self.URLS["inverterList"], data=body, headers=header)
        if response.status_code == HTTPStatus.OK:
            return response.json()["data"]["page"]["records"][0].get("sn", "")

    @property
    def inverter_details(self):
        body = self.get_body(id=self.inverter_id, sn=self.inverter_sn)
        header = self.header(body, self.URLS["inverterDetail"])
        response = requests.post(self.URLS["root"] + self.URLS["inverterDetail"], data=body, headers=header)

        if response.status_code == HTTPStatus.OK:
            return response.json()["data"]
        else:
            return {"state": 0}

    @property
    def is_online(self):
        return self.inverter_details["state"] == 1

    @property
    def last_seen(self):
        return pd.to_datetime(int(self.inverter_details["dataTimestamp"]), unit="ms")

    def read_code(self, cid):
        retries = 0
        data = "ERROR"
        while (data == "ERROR") and (retries < self.MAX_RETRIES):
            if self.token == "":
                self.login()
            body = self.get_body(inverterSn=self.inverter_sn, cid=cid)
            headers = self.header(body, self.URLS["atRead"])
            headers["token"] = self.token
            response = requests.post(self.URLS["root"] + self.URLS["atRead"], data=body, headers=headers)
            if response.status_code == HTTPStatus.OK:
                data = response.json()["data"]["msg"]
            else:
                data = "ERROR"

            if data == "ERROR":
                self.token = ""
                retries += 1
            else:
                return data

    def set_code(self, cid, value):
        if self.token == "":
            self.login()

        if self.token != "":
            body = self.get_body(inverterSn=self.inverter_sn, cid=cid, value=value)
            headers = self.header(body, self.URLS["control"])
            headers["token"] = self.token
            response = requests.post(self.URLS["root"] + self.URLS["control"], data=body, headers=headers)
            if response.status_code == HTTPStatus.OK:
                return response.json()

    def login(self):
        body = self.get_body(username=self.username, password=self.md5password)
        header = self.header(body, self.URLS["login"])
        response = requests.post(self.URLS["root"] + self.URLS["login"], data=body, headers=header)
        status = response.status_code
        if status == HTTPStatus.OK:
            result = response.json()
            self.token = result["csrfToken"]
            print("Logged in to SolisCloud OK")

        else:
            print(status)

    def read_mode_switch(self):
        bits = INVERTER_DEFS["SOLIS_CLOUD"]["bits"]
        code = int(self.read_code("636"))
        switches = {bit: (code & 2**i == 2**i) for i, bit in enumerate(bits)}
        return {"code": code, "switches": switches}

    def timed_status(self, tz="GB"):
        data = self.read_code("103").split(",")
        return {
            "charge": {
                "current": float(data[0]),
                "start": pd.Timestamp(data[2].split("-")[0], tz=tz),
                "end": pd.Timestamp(data[2].split("-")[1], tz=tz),
            },
            "discharge": {
                "current": float(data[1]),
                "start": pd.Timestamp(data[3].split("-")[0], tz=tz),
                "end": pd.Timestamp(data[3].split("-")[1], tz=tz),
            },
        }

    def read_backup_mode_soc(self):
        return int(self.read_code("157"))

    def set_mode_switch(self, code):
        return self.set_code("636", code)

    def get_time_string(self, time_status):
        time_string = ",".join(
            [
                str(int(time_status["charge"]["current"])),
                str(int(time_status["discharge"]["current"])),
                f'{time_status["charge"]["start"].strftime("%H:%M")}-{time_status["charge"]["end"].strftime("%H:%M")}',
                f'{time_status["discharge"]["start"].strftime("%H:%M")}-{time_status["discharge"]["end"].strftime("%H:%M")}',
            ]
        )
        return f"{time_string},0,0,00:00-00:00,00:00-00:00,0,0,00:00-00:00,00:00-00:00"

    def set_timer(self, direction, start, end, current):
        current_times = self.timed_status()
        new_times = current_times.copy()
        if start is not None:
            new_times[direction]["start"] = start
        if end is not None:
            new_times[direction]["end"] = end
        new_times[direction]["current"] = current
        current_time_string = self.read_code(103)
        new_time_string = self.get_time_string(new_times)
        if new_time_string != current_time_string:
            return self.set_code("103", new_time_string)
        else:
            return {"code": -1}


class InverterController:
    def __init__(self, inverter_type, host) -> None:
        self.host = host
        self.tz = self.host.tz
        if host is not None:
            self.log = host.log
        self.type = inverter_type
        self.config = {}
        self.brand_config = {}
        for defs, conf in zip(
            [INVERTER_DEFS[self.type][x] for x in ["default_config", "brand_config"]],
            [self.config, self.brand_config],
        ):
            for item in defs:
                if isinstance(defs[item], str):
                    conf[item] = defs[item].replace("{device_name}", self.host.device_name)
                elif isinstance(defs[item], list):
                    conf[item] = [z.replace("{device_name}", self.host.device_name) for z in defs[item]]
                else:
                    conf[item] = defs[item]
        if self.type == "SOLIS_CLOUD":
            params = {
                item: host.args.get(f"soliscloud_{item}")
                for item in ["username", "password", "key_id", "key_secret", "plant_id"]
            }
            if all([x is not None for x in params.values()]):
                self.cloud = SolisCloud(**params, log=self.log)
            else:
                raise Exception("Unable to create Solis Cloud controller")

    def is_online(self):
        if self.type == "SOLIS_CLOUD":
            return self.cloud.is_online
        else:
            entity_id = INVERTER_DEFS[self.type].get("online", (None, None))
            if entity_id is not None:
                entity_id = entity_id.replace("{device_name}", self.host.device_name)
                return self.host.get_state_retry(entity_id) not in ["unknown", "unavailable"]
            else:
                return True

    def enable_timed_mode(self):

        if self.type in ["SOLIS_SOLAX_MODBUS", "SOLIS_CORE_MODBUS", "SOLIS_SOLARMAN", "SOLIS_CLOUD", "SOLIS_SOLARMAN_V2"]:
            self._solis_set_mode_switch(SelfUse=True, Timed=True, GridCharge=True, Backup=False)
        else:
            self._unknown_inverter()

    def control_charge(self, enable, **kwargs):
        if enable:
            self.enable_timed_mode()
        self._control_charge_discharge("charge", enable, **kwargs)

    def control_discharge(self, enable, **kwargs):
        if enable:
            self.enable_timed_mode()
        self._control_charge_discharge("discharge", enable, **kwargs)

    # Hold SOC by setting zero charge current
    def hold_soc(self, enable, soc=None, **kwargs):

        if self.type in ["SOLIS_SOLAX_MODBUS", "SOLIS_CORE_MODBUS", "SOLIS_SOLARMAN", "SOLIS_CLOUD", "SOLIS_SOLARMAN_V2"]:

            start = kwargs.get("start", pd.Timestamp.now(tz=self.tz).floor("1min"))
            end = kwargs.get("end", pd.Timestamp.now(tz=self.tz).ceil("30min"))
            self._solis_control_charge_discharge(
                "charge",
                enable=enable,
                start=start,
                end=end,
                power=0,
            )
        else:
            self._unknown_inverter()

    def _unknown_inverter(self):
        e = f"Unknown inverter type {self.type}"
        self.log(e, level="ERROR")
        self.host.status(e)
        raise Exception(e)

    # Hold SOC by selecting backup mode
    def hold_soc_old(self, enable, soc=None):
        if self.type == "SOLIS_SOLAX_MODBUS" or self.type == "SOLIS_CORE_MODBUS" or self.type == "SOLIS_SOLARMAN" or self.type == "SOLIS_SOLARMAN_V2":

            if enable:
                self._solis_set_mode_switch(SelfUse=True, Timed=False, GridCharge=True, Backup=True)
            else:
                self.enable_timed_mode()

            # Wait for a second to make sure the mode is correct
            time.sleep(1)

            if soc is None:
                soc = self.host.get_config("maximum_dod_percent")

            entity_id = self.host.config["id_backup_mode_soc"]

            self.log(f"Setting Backup SOC to {soc}%")
            if self.type == "SOLIS_SOLAX_MODBUS":
                changed, written = self.host.write_and_poll_value(entity_id=entity_id, value=soc)
            elif self.type == "SOLIS_CORE_MODBUS" or self.type == "SOLIS_SOLARMAN" or self.type == "SOLIS_SOLARMAN_V2":
                changed, written = self.solis_write_holding_register(
                    address=INVERTER_DEFS(self.type)["registers"]["backup_mode_soc"],
                    value=soc,
                    entity_id=entity_id,
                )
        elif self.type == "SOLIS_CLOUD":
            pass
        else:
            self._unknown_inverter()

    @property
    def status(self):
        status = None

        if self.type in ["SOLIS_SOLAX_MODBUS", "SOLIS_CORE_MODBUS", "SOLIS_SOLARMAN", "SOLIS_CLOUD", "SOLIS_SOLARMAN_V2"]:

            status = self._solis_state()
        return status

    def _monitor_target_soc(self, target_soc, mode="charge"):
        pass

    def _control_charge_discharge(self, direction, enable, **kwargs):

        if self.type in ["SOLIS_SOLAX_MODBUS", "SOLIS_CORE_MODBUS", "SOLIS_SOLARMAN", "SOLIS_CLOUD", "SOLIS_SOLARMAN_V2"]:
      
            self._solis_control_charge_discharge(direction, enable, **kwargs)

    def _solis_control_charge_discharge(self, direction, enable, **kwargs):
        self.log("Entered _solis_control_charge_discharge")
        status = self._solis_state()

        times = {
            "start": kwargs.get("start", None),
            "end": kwargs.get("end", None),
        }
        power = kwargs.get("power", 0)

        if times["start"] is not None:
            times["start"] = times["start"].floor("1min")

        if not enable:
            self.log(f"Disabling inverter timed {direction}")

        else:
            self.log(f"Updating inverter {direction} control:")
            for x in kwargs:
                self.log(f"  {x}: {kwargs[x]}")

        # Disable by setting the times the same
        if (enable is not None) and (not enable):
            times["start"] = status[direction]["start"]
            times["end"] = times["start"]

        # Don't span midnight
        if times["end"] is not None:
            if times["start"] is None:
                start_day = pd.Timestamp.now().day
            else:
                start_day = times["start"].day

            if start_day != times["end"].day:
                times["end"] = times["end"].normalize() - pd.Timedelta(1, "minutes")
                self.log(f"End time clipped to {times['end'].strftime(TIMEFORMAT)}")

        write_flag = True
        value_changed = False

        if self.type in ["SOLIS_SOLAX_MODBUS", "SOLIS_SOLARMAN", "SOLIS_CORE_MODBUS", "SOLIS_SOLARMAN_V2"]:
            for limit in times:
                if times[limit] is not None:
                    if self.type == "SOLIS_SOLARMAN_V2":

                        #self.log("")
                        #self.log(f">>> Solarman V2 times, Limit = {limit}, Value {times[limit]}")

                        unit = "hours and minutes"    # Done so logging is correct
                        entity_id = self.host.config[f"id_timed_{direction}_{limit}"] 

                        #self.log("")
                        #self.log(f">>> Solarman V2 time writes: about to write {times[limit]} to entity {entity_id} using write_and_poll_time")

                        z = times[limit].tz_localize(None)
                        value = z

                        changed, written = self.host.write_and_poll_time(
                            entity_id=entity_id, value=z
                        )

                        if changed:
                            if written:
                                self.log(f"Wrote {direction} {limit} {unit} of {value} to inverter")
                                value_changed = True
                            else:
                                self.log(
                                    f"Failed to write {direction} {limit} {unit} to inverter",
                                    level="ERROR",
                                )
                                write_flag = False


                    elif self.type == "SOLIS_SOLAX_MODBUS":
                        for unit in ["hours", "minutes"]:
                            # entity_id = self.host.config[f"id_timed_{direction}_{limit}_{unit}"] 
                            if unit == "hours":
                                value = times[limit].hour
                            else:
                                value = times[limit].minute

                            entity_id = self.host.config[f"id_timed_{direction}_{limit}_{unit}"]   # moved - now only runs for Solax integration, the others don't need it. 
                            changed, written = self.host.write_and_poll_value(
                                entity_id=entity_id, value=value, verbose=True
                            )

                            if changed:
                                if written:
                                    self.log(f"Wrote {direction} {limit} {unit} of {value} to inverter")
                                    value_changed = True
                                else:
                                    self.log(
                                        f"Failed to write {direction} {limit} {unit} to inverter",
                                        level="ERROR",
                                    )
                                    write_flag = False

                    elif self.type == "SOLIS_CORE_MODBUS" or self.type == "SOLIS_SOLARMAN":
                        for unit in ["hours", "minutes"]:
                            if unit == "hours":
                                value = times[limit].hour
                            else:
                                value = times[limit].minute
                            changed, written = self._solis_write_time_register(direction, limit, unit, value)

                            if changed:
                                if written:
                                    self.log(f"Wrote {direction} {limit} {unit} of {value} to inverter")
                                    value_changed = True
                                else:
                                    self.log(
                                        f"Failed to write {direction} {limit} {unit} to inverter",
                                        level="ERROR",
                                    )
                                    write_flag = False

                    else:
                        e = "Unknown inverter type"
                        self.log(e, level="ERROR")
                        raise Exception(e)

            if value_changed:
                if self.type == "SOLIS_SOLAX_MODBUS" and write_flag:
                    entity_id = self.host.config["id_timed_charge_discharge_button"]
                    self.host.call_service("button/press", entity_id=entity_id)
                    time.sleep(0.5)

                    try:
                        time_pressed = pd.Timestamp(self.host.get_state_retry(entity_id))

                        dt = (pd.Timestamp.now(self.host.tz) - time_pressed).total_seconds()
                        if dt < 10:
                            self.log(f"Successfully pressed button {entity_id}")

                        else:
                            self.log(
                                f"Failed to press button {entity_id}. Last pressed at {time_pressed.strftime(TIMEFORMAT)} ({dt:0.2f} seconds ago)"
                            )
                    except:
                        self.log(f"Failed to press button {entity_id}: it appears to never have been pressed.")

            else:
                    self.log("Inverter already at correct time settings")

            if power is not None:
                entity_id = self.host.config[f"id_timed_{direction}_current"]

                current = abs(round(power / self.host.get_config("battery_voltage"), 1))
                current = min(current, self.host.get_config("battery_current_limit_amps"))
                self.log(f"Power {power:0.0f} = {current:0.1f}A at {self.host.get_config('battery_voltage')}V")

                if self.type == "SOLIS_SOLAX_MODBUS":
                    changed, written = self.host.write_and_poll_value(entity_id=entity_id, value=current, tolerance=1)

                elif self.type == "SOLIS_CORE_MODBUS" or self.type == "SOLIS_SOLARMAN":
                    changed, written = self._solis_write_current_register(direction, current, tolerance=1)


                elif self.type == "SOLIS_SOLARMAN_V2":
                    self.log("")
                    self.log(f">>> Solarman V2 current writes: about to write {current} to entity {entity_id}")

                    value=round(current, 1)
                    changed, written = self.host.write_and_poll_value(entity_id=entity_id, value=value, tolerance=1)      

                else:
                    e = "Unknown inverter type"
                    self.log(e, level="ERROR")
                    raise Exception(e)

                if changed:
                    if written:
                        self.log(f"Current {current}A written to inverter")
                    else:
                        self.log(f"Failed to write {current} to inverter")
                else:
                    self.log("Inverter already at correct current")
      

        elif self.type == "SOLIS_CLOUD":
            current = abs(round(power / self.host.get_config("battery_voltage"), 0))
            current = min(current, self.host.get_config("battery_current_limit_amps"))
            self.log(f"Power {power:0.0f} = {current:0.0f}A at {self.host.get_config('battery_voltage')}V")
            response = self.cloud.set_timer(direction, times["start"], times["end"], current)
            if response["code"] == -1:
                self.log("Inverter already at correct time and current settings")
            elif response["code"] == 0:
                self.log(
                    f"Wrote {direction} time of {times['start'].strftime('%H:%M')}-{times['end'].strftime('%H:%M')} to inverter"
                )
                self.log(f"Current {current}A written to inverter")
 

    def _solis_set_mode_switch(self, **kwargs):
        # Read the mode switch
        if self.type == "SOLIS_SOLAX_MODBUS" or self.type == "SOLIS_SOLARMAN" or self.type == "SOLIS_SOLARMAN_V2":
            status = self._solis_solax_solarman_mode_switch()

        elif self.type == "SOLIS_CORE_MODBUS":
            status = self._solis_core_mode_switch()

        elif self.type == "SOLIS_CLOUD":
            status = self.cloud.read_mode_switch()

        switches = status["switches"]
        if self.host.debug and "I" in self.host.debug_cat:
            self.log(f">>> kwargs: {kwargs}")
            self.log(">>> Solis switch status:")

        for switch in switches:
            if switch in kwargs:
                if (self.host.debug and "I" in self.host.debug_cat):
                    self.log(f">>> {switch}: {kwargs[switch]}")
                switches[switch] = kwargs[switch]

        # Set the mode switch
        bits = INVERTER_DEFS[self.type]["bits"]
        bin_list = [2**i * switches[bit] for i, bit in enumerate(bits)]
        code = sum(bin_list)


        if self.type != "SOLIS_CLOUD":
            entity_id = self.host.config["id_inverter_mode"]

        if self.type == "SOLIS_SOLAX_MODBUS":
            entity_modes = self.host.get_state_retry(entity_id, attribute="options")
            modes = {INVERTER_DEFS[self.type]["codes"].get(mode): mode for mode in entity_modes}
            # mode = INVERTER_DEFS[self.type]["modes"].get(code)
            mode = modes.get(code)
            if (self.host.debug and "I" in self.host.debug_cat):
                self.log(f">>> Inverter Code: {code}")
                self.log(f">>> Entity modes: {entity_modes}")
                self.log(f">>> Modes: {modes}")
                self.log(f">>> Inverter Mode: {mode}")

            self.host.set_select("inverter_mode", mode)
            #self.log("Set select inverter mode called")

        elif self.type == "SOLIS_SOLARMAN_V2":
                      
            mode = INVERTER_DEFS[self.type]["modes"].get(code)
            
            self.log("SolarMan_V2")
            self.log(f">>> Inverter Code: {code}")
            self.log(f">>> Inverter Mode: {mode}")

            self.log(f">>> Solarman_V2, writing {mode} to entity {entity_id}")
            ###
            self.host.set_select("inverter_mode", mode)
       

        elif self.type == "SOLIS_CORE_MODBUS" or self.type == "SOLIS_SOLARMAN":
            address = INVERTER_DEFS[self.type]["registers"]["storage_control_switch"]
            self._solis_write_holding_register(address=address, value=code, entity_id=entity_id)

        elif self.type == "SOLIS_CLOUD":
            self.cloud.set_mode_switch(code)

    def _solis_solax_solarman_mode_switch(self):
        inverter_mode = self.host.get_state_retry(entity_id=self.host.config["id_inverter_mode"])
        if self.type == "SOLIS_SOLAX_MODBUS":
            code = INVERTER_DEFS[self.type]["codes"][inverter_mode]
        else:
            modes = INVERTER_DEFS[self.type]["modes"]
            code = {modes[m]: m for m in modes}[inverter_mode]
        if (self.host.debug and "I" in self.host.debug_cat):
            self.log(f">>> Inverter Mode: {inverter_mode}")
            self.log(f">>> Inverter Code: {code}")

        bits = INVERTER_DEFS[self.type]["bits"]
        switches = {bit: (code & 2**i == 2**i) for i, bit in enumerate(bits)}
        return {"mode": inverter_mode, "code": code, "switches": switches}

    def _solis_core_mode_switch(self):
        bits = INVERTER_DEFS["SOLIS_CORE_MODBUS"]["bits"]
        code = int(self.host.get_state_retry(entity_id=self.host.config["id_inverter_mode"]))
        switches = {bit: (code & 2**i == 2**i) for i, bit in enumerate(bits)}
        return {"code": code, "switches": switches}


    def _solis_state(self):
        limits = ["start", "end"]
      
        if self.type == "SOLIS_SOLAX_MODBUS" or self.type == "SOLIS_SOLARMAN" or self.type == "SOLIS_SOLARMAN_V2":
            status = self._solis_solax_solarman_mode_switch()
        elif self.type == "SOLIS_CORE_MODBUS":
            status = self._solis_core_mode_switch()
        elif self.type == "SOLIS_CLOUD":
            status = self.cloud.read_mode_switch()


        if self.type in ["SOLIS_SOLAX_MODBUS", "SOLIS_SOLARMAN", "SOLIS_CORE_MODBUS", "SOLIS_SOLARMAN_V2"]:        
            for direction in ["charge", "discharge"]:
                status[direction] = {
                    "current": 0,
                    "start": pd.Timestamp("00:00", tz=self.tz),
                    "end": pd.Timestamp("00:00", tz=self.tz),
                }
                for limit in limits:
                    states = {}
                    if self.type == "SOLIS_SOLARMAN" or self.type == "SOLIS_SOLAX_MODBUS" or self.type == "SOLIS_CORE_MODBUS":                
                        for unit in ["hours", "minutes"]:
                            entity_id = self.host.config[f"id_timed_{direction}_{limit}_{unit}"]
                            states[unit] = int(float(self.host.get_state_retry(entity_id=entity_id)))

                        status[direction][limit] = pd.Timestamp(
                            f"{states['hours']:02d}:{states['minutes']:02d}", tz=self.host.tz
                        )
                        ### SVB debugging
                        #self.log("Status of status is....")
                        #self.log(status[direction][limit])

                    else:   # for SOLARMAN_V2

                        #Code for combined hours/minutes entity
                        entity_id = self.host.config[f"id_timed_{direction}_{limit}"]
                        time_stamp = (self.host.get_state_retry(entity_id=entity_id))
                        status[direction][limit] = pd.Timestamp(time_stamp, tz=self.host.tz)

                time_now = pd.Timestamp.now(tz=self.tz)
                entity_id = self.host.config[f"id_timed_{direction}_current"]
                status[direction]["current"] = float(self.host.get_state_retry(entity_id))
                

        elif self.type == "SOLIS_CLOUD":
            status = status | self.cloud.timed_status(tz=self.host.tz)

        time_now = pd.Timestamp.now(tz=self.tz)
        for direction in ["charge", "discharge"]:
            status[direction]["active"] = (
                time_now >= status[direction]["start"]
                and time_now < status[direction]["end"]
                and status[direction].get("current", 0) >= 0 # SVB changed to ">=" so IOG slots are seen as charging (as they effectively use timed charge)
                and status["switches"].get("Timed", False)
                and status["switches"].get("GridCharge", False)
            )

        status["hold_soc"] = {"active": status["switches"]["Backup"]}
        if self.type == "SOLIS_SOLAX_MODBUS" or self.type == "SOLIS_CORE_MODBUS": ### Needs SOLARMAN_V2 adding, as backup mode register is now supported
            status["hold_soc"]["soc"] = self.host.get_config("id_backup_mode_soc")
        elif self.type == "SOLIS_CLOUD":
            status["hold_soc"]["soc"] = self.cloud.read_backup_mode_soc()
        else:
            status["hold_soc"]["soc"] = None  ### SOLARMAN_V2 has the ability to read id_backup_mode_SOC so should probably add to the switch above

        return status

    def _solis_write_holding_register(
        self,
        address,
        value,
        entity_id=None,
        tolerance=0,
        multiplier=1,
    ):
        changed = True
        written = False
        if self.type == "SOLIS_CORE_MODBUS":
            hub = self.host.get_config("modbus_hub")
            slave = self.host.get_config("modbus_slave")

            if entity_id is not None:
                old_value = int(float(self.host.get_state_retry(entity_id=entity_id)))
                if isinstance(old_value, int) and abs(old_value - value) <= tolerance:
                    self.log(f"Inverter value already set to {value}.")
                    changed = False

            if changed:
                data = {
                    "address": address,
                    "slave": slave,
                    "value": int(round(value * multiplier, 0)),
                    "hub": hub,
                }
                self.host.call_service("modbus/write_register", **data)
                written = True

        elif self.type == "SOLIS_SOLARMAN":
            if entity_id is not None and self.host.entity_exists(entity_id):
                old_value = int(float(self.host.get_state_retry(entity_id=entity_id)))
                if isinstance(old_value, int) and abs(old_value - value) <= tolerance:
                    self.log(f"Inverter value already set to {value}.")
                    changed = False

            if changed:
                data = {"register": address, "value": value}
                # self.host.call_service("solarman/write_holding_register", **data)
                # self.log(">>> Writing {value} to inverter register {address} using Solarman")
                written = True

        return changed, written

    def _solis_write_current_register(self, direction, current, tolerance):
        address = INVERTER_DEFS[self.type]["registers"][f"timed_{direction}_current"]
        entity_id = self.host.config[f"id_timed_{direction}_current"]
        return self._solis_write_holding_register(
            address=address,
            value=round(current, 1),
            entity_id=entity_id,
            tolerance=tolerance,
            multiplier=10,
        )

    def _solis_write_time_register(self, direction, limit, unit, value):
        address = INVERTER_DEFS[self.type]["registers"][f"timed_{direction}_{limit}_{unit}"]
        entity_id = self.host.config[f"id_timed_{direction}_{limit}_{unit}"] #

        return self._solis_write_holding_register(address=address, value=value, entity_id=entity_id)
