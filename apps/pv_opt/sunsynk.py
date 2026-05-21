import base64
import hashlib
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from time import sleep

import numpy as np
import pandas as pd
import requests
from cryptography.hazmat.primitives.asymmetric.padding import PKCS1v15
from cryptography.hazmat.primitives.serialization import load_pem_public_key

TIMEFORMAT = "%H:%M"

INVERTER_DEFS = {
    "SUNSYNK_SOLARSYNKV3": {
        "online": "sensor.{device_name}_{inverter_sn}_battery_soc",
        "default_config": {
            "maximum_dod_percent": 20,
            "id_battery_soc": "sensor.{device_name}_{inverter_sn}_battery_soc",
            "id_consumption_today": "sensor.{device_name}_{inverter_sn}_load_daily_used",
            "id_consumption": "sensor.{device_name}_{inverter_sn}_load_power",   # not believed used
            "id_grid_import_today": "sensor.{device_name}_{inverter_sn}_grid_etoday_from",
            "id_grid_export_today": "sensor.{device_name}_{inverter_sn}_grid_etoday_to",
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
            "battery_current": "sensor.{device_name}_{inverter_sn}_battery_current",   # not believed used
            "id_control_helper": "input_text.{device_name}_{inverter_sn}_settings", 
            "id_use_timer": "sensor.{device_name}_{inverter_sn}_peakandvallery",    
            "id_priority_load": "sensor.{device_name}_{inverter_sn}_energymode",    
            "id_timed_charge_start": "sensor.{device_name}_{inverter_sn}_selltime1", 
            "id_timed_charge_end": "sensor.{device_name}_{inverter_sn}_selltime2",   
            "id_timed_charge_enable": "sensor.{device_name}_{inverter_sn}_gentime1on",  
            "id_timed_charge_target_soc": "sensor.{device_name}_{inverter_sn}_cap1",  
            "id_timed_charge_capacity": "sensor.{device_name}_{inverter_sn}_prog1_capacity",  # not believed used
            "id_timed_discharge_start": "sensor.{device_name}_{inverter_sn}_selltime3",
            "id_timed_discharge_end": "sensor.{device_name}_{inverter_sn}_selltime4",
            "id_timed_dicharge_enable": "sensor.{device_name}_{inverter_sn}_gentime3on", 
            "id_timed_discharge_target_soc": "sensor.{device_name}_{inverter_sn}_cap3", 
            "id_timed_discharge_capacity": "sensor.{device_name}_{inverter_sn}_prog3_capacity",   # not believed used
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
                self._brand_config["json_timed_charge_start"]: kwargs.get("start", time_now.strftime(TIMEFORMAT)),
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
                self._brand_config["json_charge_current"]: self._host.get_config("battery_current_limit_amps"),
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
                self._brand_config["json_timed_discharge_start"]: kwargs.get("start", time_now.strftime(TIMEFORMAT)),
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

    @property
    def status(self):
        """Read current inverter status from HA entities exposed by the martinville/solarsynkv3 addon."""
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
                    current_dict = dict(pair.split(":", 1) for pair in current_state[3:].split(";") if ":" in pair)
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
                self._brand_config["json_timed_charge_start"]: kwargs.get("start", time_now.strftime(TIMEFORMAT)),
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
                self._brand_config["json_charge_current"]: self._host.get_config("battery_current_limit_amps"),
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
                self._brand_config["json_timed_discharge_start"]: kwargs.get("start", time_now.strftime(TIMEFORMAT)),
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

    def _authenticate(self) -> str:
        """Authenticate with the Sunsynk API and return a Bearer token.

        Uses RSA public key encryption for the password, matching the
        authentication flow in the Solar-Sunsynk integration.

        Returns:
            str: Bearer token on success, empty string on failure.
        """
        base_url = "https://api.sunsynk.net"
        username = self._host.get_config("sunsynk_username")
        password = self._host.get_config("sunsynk_password")

        if not username or not password:
            self.log("sunsynk_username or sunsynk_password not set in config", level="ERROR")
            return ""

        try:
            # Fetch RSA public key
            nonce = str(int(time.time() * 1000))
            sign = hashlib.md5(f"nonce={nonce}&source=sunsynkPOWER_VIEW".encode()).hexdigest()
            resp = requests.get(
                f"{base_url}/anonymous/publicKey",
                params={"source": "sunsynk", "nonce": nonce, "sign": sign},
                timeout=10,
            )
            resp.raise_for_status()
            public_key_string = str(resp.json()["data"])

            # Encrypt password with RSA public key
            pem = "-----BEGIN PUBLIC KEY-----\n" + public_key_string + "\n-----END PUBLIC KEY-----"
            public_key = load_pem_public_key(pem.encode())
            encrypted_password = base64.b64encode(public_key.encrypt(password.encode(), PKCS1v15())).decode()

            # Obtain Bearer token
            token_nonce = str(int(time.time() * 1000))
            token_sign = hashlib.md5(
                f"nonce={token_nonce}&source=sunsynk{public_key_string[:10]}".encode()
            ).hexdigest()

            resp = requests.post(
                f"{base_url}/oauth/token/new",
                json={
                    "client_id": "csp-web",
                    "grant_type": "password",
                    "password": encrypted_password,
                    "source": "sunsynk",
                    "username": username,
                    "nonce": token_nonce,
                    "sign": token_sign,
                },
                timeout=10,
            )
            resp.raise_for_status()
            resp_json = resp.json()

            if resp_json.get("msg") != "Success":
                self.log(f"Sunsynk authentication failed: {resp_json.get('msg')}", level="ERROR")
                return ""

            return str(resp_json["data"]["access_token"])

        except Exception as e:
            self.log(f"Sunsynk authentication error: {e}", level="ERROR")
            return ""

    def _get_inverter_settings(self) -> dict:
        """Fetch current inverter settings directly from the Sunsynk cloud API.

        Returns:
            dict: Settings data dict (e.g. sellTime1, cap1, time1on etc.)
                  Returns empty dict on failure.
        """
        sn = self._inverter_sn
        if not sn:
            self.log("inverter_sn not set in config.yaml", level="ERROR")
            return {}

        token = self._authenticate()
        if not token:
            return {}

        try:
            resp = requests.get(
                f"https://api.sunsynk.net/api/v1/common/setting/{sn}/read",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            resp.raise_for_status()
            resp_json = resp.json()

            if resp_json.get("msg") != "Success":
                self.log(f"Sunsynk settings fetch failed: {resp_json.get('msg')}", level="ERROR")
                return {}

            return resp_json.get("data", {})

        except Exception as e:
            self.log(f"Sunsynk settings fetch error: {e}", level="ERROR")
            return {}

    def _set_inverter(self, **kwargs):
        converted = self._convert_kwargs(kwargs)
        sn = self._inverter_sn
        self.log(f"Calling solar_sunsynk.set_solar_settings for inverter {sn} with {converted}")
        self._host.call_service(
            "solar_sunsynk/set_solar_settings",
            sn=sn,
            **converted,
        )

    @property
    def status(self):
        """Read current inverter status directly from the Sunsynk cloud API."""
        time_now = pd.Timestamp.now(tz=self.tz)
        bc = self._brand_config

        self.log("Fetching inverter settings from Sunsynk API for status check")
        settings = self._get_inverter_settings()

        if not settings:
            self.log("Unable to fetch inverter settings — returning empty status", level="WARNING")
            return None

        def _parse_time(t):
            try:
                return pd.Timestamp(f"{pd.Timestamp.now(tz=self.tz).date()} {t}", tz=self.tz)
            except Exception:
                return None

        charge_start = _parse_time(settings.get(bc["json_timed_charge_start"], "00:00"))
        charge_end = _parse_time(settings.get(bc["json_timed_charge_end"], "00:00"))
        discharge_start = _parse_time(settings.get(bc["json_timed_discharge_start"], "00:00"))
        discharge_end = _parse_time(settings.get(bc["json_timed_discharge_end"], "00:00"))
        charge_enable = settings.get(bc["json_timed_charge_enable"], False)
        discharge_enable = settings.get(bc["json_timed_discharge_enable"], False)

        return {
            "timer mode": settings.get(bc["json_use_timer"]),
            "priority load": settings.get(bc["json_priority_load"]),
            "charge": {
                "start": charge_start,
                "end": charge_end,
                "active": charge_enable
                and charge_start is not None
                and charge_end is not None
                and (time_now >= charge_start)
                and (time_now < charge_end),
                "target_soc": settings.get(bc["json_timed_charge_target_soc"]),
            },
            "discharge": {
                "start": discharge_start,
                "end": discharge_end,
                "active": discharge_enable
                and discharge_start is not None
                and discharge_end is not None
                and (time_now >= discharge_start)
                and (time_now < discharge_end),
                "target_soc": settings.get(bc["json_timed_discharge_target_soc"]),
            },
            "hold_soc": {
                "active": False,
                "soc": 0.0,
            },
        }


# Legacy compatibility: InverterController is kept as an alias so any existing
# code that instantiates InverterController directly continues to work.
# New code should use create_inverter_controller() instead.
class InverterController(SunsynkInverterController):
    """Legacy entry point — wraps the correct subclass for the inverter type."""

    def __init__(self, inverter_type: str, host) -> None:
        self._delegate = create_inverter_controller(inverter_type=inverter_type, host=host)
        super().__init__(inverter_type=inverter_type, host=host)

    def _set_inverter(self, **kwargs):
        self._delegate._set_inverter(**kwargs)

    def enable_timed_mode(self):
        self._delegate.enable_timed_mode()

    def control_charge(self, enable, **kwargs):
        self._delegate.control_charge(enable, **kwargs)

    def control_discharge(self, enable, **kwargs):
        self._delegate.control_discharge(enable, **kwargs)

    def hold_soc(self, enable, soc=None):
        self._delegate.hold_soc(enable, soc=soc)

    @property
    def status(self):
        return self._delegate.status

    @property
    def is_online(self):
        return self._delegate.is_online

    @property
    def timed_mode(self):
        return self._delegate.timed_mode

    def clear_hold_status(self):
        self._delegate.clear_hold_status()
