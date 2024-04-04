# %%
import appdaemon.plugins.hass.hassapi as hass
import appdaemon.adbase as ad
import appdaemon.plugins.mqtt.mqttapi as mqtt
from json import dumps

import pandas as pd
import time

import pvpy as pv
import numpy as np
from numpy import nan
import re

VERSION = "4.0.0-sunsynk-alpha-16"

OCTOPUS_PRODUCT_URL = r"https://api.octopus.energy/v1/products/"

DEBUG = False

DATE_TIME_FORMAT_LONG = "%Y-%m-%d %H:%M:%S%z"
DATE_TIME_FORMAT_SHORT = "%d-%b %H:%M %Z"
TIME_FORMAT = "%H:%M"

REDACT_REGEX = [
    "[0-9]{2}m[0-9]{7}_[0-9]{13}",  # Serial_MPAN
    "[0-9]{2}e[0-9]{7}_[0-9]{13}",  # Serial_MPAN
    "[0-9]{2}m[0-9]{7}",  # Serial
    "[0-9]{2}e[0-9]{7}",  # Serial
    "^$|\d{13}$",  # MPAN
    "a_[0-f]{8}",  # Account Number
    "A-[0-f]{8}",  # Account Number
    "sk_live_[a-zA-Z0-9]{24}",  # API
]

EVENT_TRIGGER = "PV_OPT"
DEBUG_TRIGGER = "PV_DEBUG"
HOLD_TOLERANCE = 3
MAX_ITERS = 10
MAX_INVERTER_UPDATES = 2
MAX_HASS_HISTORY_CALLS = 5
OVERWRITE_ATTEMPTS = 5
ONLINE_RETRIES = 12
WRITE_POLL_SLEEP = 0.5
WRITE_POLL_RETRIES = 5
GET_STATE_RETRIES = 5
GET_STATE_WAIT = 0.5

BOTTLECAP_DAVE = {
    "domain": "event",
    "tariff_code": "tariff_code",
    "rates": "current_day_rates",
}

CONSUMPTION_SHAPE = {
    "hour": [0, 0.5, 6, 8, 15.5, 17, 22, 24],
    "consumption": [300, 200, 150, 500, 500, 750, 750, 300],
}

INVERTER_TYPES = ["SOLIS_SOLAX_MODBUS", "SOLIS_CORE_MODBUS", "SOLIS_SOLARMAN", "SUNSYNK_SOLARSYNK2", "SOLAX_X1"]

SYSTEM_ARGS = [
    "module",
    "class",
    "prefix",
    "log",
    "dependencies",
    "overwrite_ha_on_restart",
    "debug",
    "redact_personal_data_from_log",
    "list_entities",
]

IMPEXP = ["import", "export"]

MQTT_CONFIGS = {
    "switch": {
        "payload_on": "ON",
        "payload_off": "OFF",
        "state_on": "ON",
        "state_off": "OFF",
    },
    "number": {
        "mode": "slider",
    },
    "text": {
        "pattern": "^([0-1]?[0-9]|2[0-3]):[0-5][0-9]",
    },
}

DOMAIN_ATTRIBUTES = {
    "number": ["min", "max", "step"],
    "sensor": [],
    "select": ["options"],
}

DEFAULT_CONFIG = {
    "read_only": {"default": True, "domain": "switch"},
    "include_export": {"default": True, "domain": "switch"},
    "forced_discharge": {"default": True, "domain": "switch"},
    "allow_cyclic": {"default": False, "domain": "switch"},
    "use_solar": {"default": True, "domain": "switch"},
    "optimise_frequency_minutes": {
        "default": 10,
        "attributes": {
            "min": 5,
            "max": 30,
            "step": 5,
            "mode": "slider",
        },
        "domain": "number",
    },
    "test_start": {"default": "00:00", "domain": "text", "min": 5, "max": 5},
    "test_end": {"default": "00:00", "domain": "text", "min": 5, "max": 5},
    "test_power": {
        "default": 3000,
        "domain": "number",
        "attributes": {
            "min": 1000,
            "max": 10000,
            "step": 100,
            "unit_of_measurement": "W",
            "device_class": "power",
            "mode": "slider",
        },
    },
    "test_target_soc": {
        "default": 100,
        "domain": "number",
        "attributes": {
            "min": 0,
            "max": 100,
            "step": 1,
            "unit_of_measurement": "%",
            "device_class": "battery",
            "mode": "slider",
        },
    },
    "test_enable": {
        "default": "Enable",
        "domain": "select",
        "attributes": {"options": ["Enable", "Disable"]},
    },
    "test_function": {
        "default": "Charge",
        "domain": "select",
        "attributes": {"options": ["Charge", "Discharge"]},
    },
    "test_button": {
        "default": pd.Timestamp.now(tz="UTC"),
        "name": "Test",
        "domain": "button",
    },
    "solcast_confidence_level": {
        "default": 50,
        "attributes": {
            "min": 10,
            "max": 90,
            "step": 10,
            "mode": "slider",
        },
        "domain": "number",
    },
    "slot_threshold_p": {
        "default": 1.0,
        "attributes": {
            "min": 0.0,
            "max": 3.0,
            "step": 0.1,
            "mode": "slider",
        },
        "domain": "number",
    },
    "day_of_week_weighting": {
        "default": 0.5,
        "attributes": {
            "min": 0.0,
            "max": 1.0,
            "step": 0.1,
            "mode": "slider",
        },
        "domain": "number",
    },
    "pass_threshold_p": {
        "default": 4.0,
        "attributes": {
            "min": 0.0,
            "max": 1.0,
            "step": 0.5,
            "mode": "slider",
        },
        "domain": "number",
    },
    "plunge_threshold_p_kwh": {
        "default": 2.0,
        "attributes": {
            "min": -5.0,
            "max": 10.0,
            "step": 0.5,
            "mode": "box",
        },
        "domain": "number",
    },
    "discharge_threshold_p": {
        "default": 5.0,
        "attributes": {
            "min": 0.0,
            "max": 1000.0,
            "step": 5,
            "mode": "box",
        },
        "domain": "number",
    },
    "octopus_auto": {"default": True, "domain": "switch"},
    "battery_capacity_wh": {
        "default": 10000,
        "domain": "number",
        "attributes": {
            "min": 2000,
            "max": 20000,
            "step": 100,
            "unit_of_measurement": "Wh",
            "device_class": "energy",
            "mode": "slider",
        },
    },
    "inverter_efficiency_percent": {
        "default": 97,
        "domain": "number",
        "attributes": {
            "min": 90,
            "max": 100,
            "step": 1,
            "unit_of_measurement": "%",
            "mode": "slider",
        },
    },
    "charger_efficiency_percent": {
        "default": 91,
        "domain": "number",
        "attributes": {
            "min": 80,
            "max": 100,
            "step": 1,
            "unit_of_measurement": "%",
            "mode": "slider",
        },
    },
    "charger_power_watts": {
        "default": 3000,
        "domain": "number",
        "attributes": {
            "min": 1000,
            "max": 10000,
            "step": 100,
            "unit_of_measurement": "W",
            "device_class": "power",
            "mode": "slider",
        },
    },
    "inverter_power_watts": {
        "default": 3600,
        "domain": "number",
        "attributes": {
            "min": 1000,
            "max": 10000,
            "step": 100,
            "unit_of_measurement": "W",
            "device_class": "power",
            "mode": "slider",
        },
    },
    "inverter_loss_watts": {
        "default": 100,
        "domain": "number",
        "attributes": {
            "min": 0,
            "max": 300,
            "step": 10,
            "unit_of_measurement": "W",
            "device_class": "power",
            "mode": "slider",
        },
    },
    "ev_charger_power_watts": {
        "default": 7000,
        "domain": "number",
        "attributes": {
            "min": 1000,
            "max": 10000,
            "step": 100,
            "unit_of_measurement": "W",
            "device_class": "power",
            "mode": "slider",
        },
    },
    "ev_battery_capacity_kwh": {
        "default": 30,
        "domain": "number",
        "attributes": {
            "min": 5,
            "max": 600,
            "step": 1,
            "unit_of_measurement": "kWh",
            "device_class": "energy",
            "mode": "slider",
        },
    },
    "ev_charger": {
        "default": "None",
        "attributes": {
            "options": [
                "None",
                "Zappi",
                "Other",
            ]
        },
        "domain": "select",
    },
    "solar_forecast": {
        "default": "Solcast",
        "attributes": {"options": ["Solcast", "Solcast_p10", "Solcast_p90", "Weighted"]},
        "domain": "select",
    },
    "id_solcast_today": {"default": "sensor.solcast_pv_forecast_forecast_today"},
    "id_solcast_tomorrow": {"default": "sensor.solcast_pv_forecast_forecast_tomorrow"},
    "use_consumption_history": {"default": True, "domain": "switch"},
    "consumption_history_days": {
        "default": 7,
        "domain": "number",
        "attributes": {
            "min": 1,
            "max": 28,
            "step": 1,
            "mode": "slider",
        },
    },
    "consumption_margin": {
        "default": 10,
        "domain": "number",
        "attributes": {
            "min": -50,
            "max": 100,
            "step": 5,
            "unit_of_measurement": "%",
            "mode": "slider",
        },
    },
    "daily_consumption_kwh": {
        "default": 17,
        "domain": "number",
        "attributes": {
            "min": 1,
            "max": 50,
            "step": 1,
            "mode": "slider",
        },
    },
    "shape_consumption_profile": {"default": True, "domain": "switch"},
    "consumption_grouping": {
        "default": "mean",
        "domain": "select",
        "attributes": {"options": ["mean", "median", "max"]},
    },
    "forced_power_group_tolerance": {
        "default": 100,
        "domain": "number",
        "attributes": {
            "min": 0,
            "max": 1000,
            "step": 100,
            "unit_of_measurement": "W",
            "device_class": "power",
            "mode": "slider",
        },
    },
    # "alt_tariffs": {"default": [], "domain": "input_select"},
}


def importName(modulename, name):
    """Import a named object from a module in the context of this function."""
    try:
        module = __import__(modulename, globals(), locals(), [name])
    except ImportError:
        return None
    return vars(module)[name]


class PVOpt(hass.Hass):
    @ad.app_lock
    def initialize(self):
        self.config = {}
        self.log("")
        self.log(f"******************* PV Opt v{VERSION} *******************")
        self.log("")

        self.debug = DEBUG
        self.redact_regex = REDACT_REGEX

        try:
            subver = int(VERSION.split(".")[2])
        except:
            self.log("Pre-release version. Enabling debug logging")
            self.debug = True

        self.debug = self.args.get("debug", self.debug)

        self.adapi = self.get_ad_api()
        self.mqtt = self.get_plugin_api("MQTT")
        self._load_tz()
        self.log(f"Time Zone Offset: {self.get_tz_offset()} minutes")

        # self.log(self.args)
        self.inverter_type = self.args.pop("inverter_type", "SOLIS_SOLAX_MODBUS")
        self.device_name = self.args.pop("device_name", "solis")

        self.redact = self.args.pop("redact_personal_data_from_log", True)

        self.inverter_sn = self.args.pop("inverter_sn", "")
        if self.inverter_sn != "":
            self.redact_regex.append(self.inverter_sn)

        self.redact = self.args.pop("redact_personal_data_from_log", True)
        self._load_inverter()

        retry_count = 0
        while (not self.inverter.is_online()) and (retry_count < ONLINE_RETRIES):
            self.log("Inverter controller appears not to be running. Waiting 5 secomds to re-try")
            time.sleep(5)
            retry_count += 1

        if not self.inverter.is_online():
            e = "Unable to get expected response from Inverter Controller for {self.inverter_type}"
            self._status(e)
            self.log(e, level="ERROR")
            raise Exception(e)
        else:
            self.log("Inverter appears to be online")

        if self.debug or self.args.get("list_entities", True):
            self._list_entities()

        self.change_items = {}
        self.config_state = {}
        self.timer_handle = None
        self.handles = {}
        self.mqtt_handles = {}

        self.mpans = []

        self.saving_events = {}
        self.contract = None

        self.bottlecap_entities = {"import": None, "export": None}

        # Load arguments from the YAML file
        # If there are none then use the defaults in DEFAULT_CONFIG and DEFAULT_CONFIG_BY_BRAND
        # if there are existing entities for the configs in HA then read those values
        # if not, set up entities using MQTT discovery and write the initial state to them
        self._load_args()

        # self._estimate_capacity()
        self._load_pv_system_model()
        self._load_contract()
        self._check_for_zappi()

        if self.get_config("alt_tariffs") is not None:
            self._compare_tariffs()
            self._setup_compare_schedule()

        # if self.agile:
        #     self._setup_agile_schedule()

        self._cost_actual()

        # Optimise on an EVENT trigger:
        self.listen_event(
            self.optimise_event,
            EVENT_TRIGGER,
        )

        if not self.get_config("read_only"):
            self.inverter.enable_timed_mode()

        self.log("")
        self.log("Running initial Optimisation:")
        self.optimise()
        self._setup_schedule()

        if self.debug:
            self.log(f"PV Opt Initialisation complete. Listen_state Handles:")
            for id in self.handles:
                self.log(f"  {id} {self.handles[id]}  {self.info_listen_state(self.handles[id])}")

    @ad.app_lock
    def _run_test(self):
        self.ulog("Test")

        test = {
            item: self.get_ha_value(self.ha_entities[f"test_{item}"])
            for item in ["start", "end", "power", "enable", "function", "target_soc"]
        }

        for x in ["start", "end"]:
            test[x] = pd.Timestamp(test[x], tz=self.tz)

        test["enable"] = test["enable"].lower() == "enable"
        function = test.pop("function").lower()

        self._log_inverter_status(self.inverter.status)

        if function == "charge":
            self.inverter.control_charge(**test)

        elif function == "discharge":
            self.inverter.control_discharge(**test)

        else:
            pass

        if self.get_config("update_cycle_seconds") is not None:
            i = int(self.get_config("update_cycle_seconds") * 1.2)
            self.log(f"Waiting for Modbus Read cycle: {i} seconds")
            while i > 0:
                self._status(f"Waiting for Modbus Read cycle: {i}")
                time.sleep(1)
                i -= 1

        self._log_inverter_status(self.inverter.status)

    def _check_for_io(self):
        self.ulog("Checking for Intelligent Octopus")
        entity_id = f"binary_sensor.octopus_energy_{self.get_config('octopus_account').lower().replace('-', '_')}_intelligent_dispatching"
        self.rlog(f">>> {entity_id}")
        io_dispatches = self.get_state(entity_id)
        self.log(f">>> IO entity state:  {io_dispatches}")
        self.io = io_dispatches is not None
        if self.io:
            self.rlog(f"IO entity {entity_id} found")
            self.log("")
            self.io_entity = entity_id

    def _get_io(self):
        self.ulog("Intelligent Octopus Status")
        self.io_dispatch_active = self.get_state(self.io_entity)
        self.log(f"  Active: {self.io_dispatch_active}")
        self.log("")
        self.io_dispatch_attrib = self.get_state(self.io_entity, attribute="all")
        for k in [x for x in self.io_dispatch_attrib.keys() if "dispatches" not in x]:
            self.log(f" {k:20s} {self.io_dispatch_attrib[k]}")

        for k in [x for x in self.io_dispatch_attrib.keys() if "dispatches" in x]:
            self.log(f"  {k:20s} {'Start':20s} {'End':20s} {'Charge':12s} {'Source':12s}")
            self.log(f"  {'-'*20} {'-'*20} {'-'*20} {'-'*12} {'-'*12} ")
            for z in self.io_dispatch_attrib[k]:
                self.log(
                    f"  {z['start'].strftime(DATE_TIME_FORMAT_LONG):20s}  {z['end'].strftime(DATE_TIME_FORMAT_LONG):20s}  {z['charge_in_kwh']:12.3f}  {z['source']:12s}"
                )
            self.log("")

    def _check_for_zappi(self):
        self.ulog("Checking for Zappi Sensors")
        sensor_entities = self.get_state("sensor")
        self.zappi_entities = [k for k in sensor_entities if "zappi" in k for x in ["charge_added_session"] if x in k]
        if len(self.zappi_entities) > 0:
            for entity_id in self.zappi_entities:
                zappi_sn = entity_id.split("_")[2]
                self.redact_regex.append(zappi_sn)
                self.rlog(f"  {entity_id}")
        else:
            self.log("No Zappi sensors found")
        self.log("")

    def _get_zappi(self, **kwargs):
        for entity_id in self.zappi_entities:
            df = self.hass2df(entity_id=entity_id, **kwargs)
            self.rlog(f">>> Zappi entity {entity_id}")
            self.log(f">>> {df.to_string()}")

    def rlog(self, str, **kwargs):
        if self.redact:
            try:
                for pattern in self.redact_regex:
                    x = re.search(pattern, str)
                    if x:
                        str = re.sub(pattern, "*" * len(x.group()), str)
            except:
                pass

        self.log(str, **kwargs)

    def _estimate_capacity(self):
        if "id_battery_charge_power" in self.config:
            df = pd.DataFrame(
                self.hass2df(
                    entity_id=self.config["id_battery_charge_power"],
                    days=7,
                    log=self.debug,
                ).astype(int, errors="ignore")
            ).set_axis(["Power"], axis=1)

            df["period"] = (df["Power"] > 200).diff().abs().cumsum()
            df["dt"] = -df.index.diff(-1).total_seconds() / 3600
            df["Energy"] = df["dt"] * df["Power"]
            x = df.groupby("period").sum()
            p = x[x["Energy"] == x["Energy"].max()].index[0]
            start = df[df["period"] == p].index[0]
            end = df[df["period"] == p].index[-1]
            soc = (
                self.hass2df(entity_id=self.config["id_battery_soc"], days=7)
                .astype(int, errors="ignore")
                .loc[start:end]
            )
            start = soc.index[0]
            end = soc.index[-1]
            energy = df.loc[start:end]["Energy"].sum()
            dsoc = soc.iloc[-1] - soc.iloc[0]

            return energy * 100 / dsoc
        else:
            return None

    def _load_tz(self):
        self.tz = self.args.pop("manual_tz", "GB")
        self.log(f"Local timezone set to {self.tz}")

    def _load_inverter(self):
        if self.inverter_type in INVERTER_TYPES:
            inverter_brand = self.inverter_type.split("_")[0].lower()
            InverterController = importName(f"{inverter_brand}", "InverterController")
            self.log(f"Inverter type: {self.inverter_type}: inverter module: {inverter_brand}.py")
            self.inverter = InverterController(inverter_type=self.inverter_type, host=self)
            self.log(f"  Device name:   {self.device_name}")
            self.log(f"  Serial number: {self.inverter_sn}")

        else:
            e = f"Inverter type {self.inverter_type} is not yet supported. Only read-only mode with explicit config from the YAML will work."
            self.log(e, level="ERROR")

    def _load_pv_system_model(self):
        self._status("Initialising PV Model")

        self.inverter_model = pv.InverterModel(
            inverter_efficiency=self.get_config("inverter_efficiency_percent") / 100,
            inverter_power=self.get_config("inverter_power_watts"),
            inverter_loss=self.get_config("inverter_loss_watts"),
            charger_efficiency=self.get_config("charger_efficiency_percent") / 100,
            charger_power=self.get_config("charger_power_watts"),
        )

        self.battery_model = pv.BatteryModel(
            capacity=self.get_config("battery_capacity_wh"),
            max_dod=self.get_config("maximum_dod_percent") / 100,
        )
        self.pv_system = pv.PVsystemModel("PV_Opt", self.inverter_model, self.battery_model, host=self)

    # def _setup_agile_schedule(self):
    #     start = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(1, "minutes")).to_pydatetime()
    #     self.timer_handle = self.run_every(
    #         self._load_agile_cb,
    #         start=start,
    #         interval=3600,
    #     )

    def _setup_compare_schedule(self):
        start = (pd.Timestamp.now(tz="UTC").ceil("60min") - pd.Timedelta("2min")).to_pydatetime()
        self.timer_handle = self.run_every(
            self._compare_tariff_cb,
            start=start,
            interval=3600,
        )

    def _cost_actual(self, **kwargs):
        start = kwargs.get("start", pd.Timestamp.now(tz="UTC").normalize())
        end = kwargs.get("end", pd.Timestamp.now(tz="UTC"))

        if self.debug:
            self.log(
                f">>> Start: {start.strftime(DATE_TIME_FORMAT_SHORT)} End: {end.strftime(DATE_TIME_FORMAT_SHORT)}"
            )
        days = (pd.Timestamp.now(tz="UTC") - start).days + 1

        index = pd.date_range(
            start,
            end,
            freq="30min",
        )
        cols = ["grid_import", "grid_export"]
        grid = pd.DataFrame()
        for col in cols:
            entity_id = self.config[f"id_{col}_today"]
            df = self._get_hass_power_from_daily_kwh(entity_id, start=start, end=end)
            grid = pd.concat([grid, df], axis=1)

        grid = grid.set_axis(cols, axis=1).fillna(0)
        grid["grid_export"] *= -1

        cost_today = self.contract.net_cost(grid_flow=grid, log=self.debug, day_ahead=False)

        return cost_today

    @ad.app_lock
    def _compare_tariff_cb(self, cb_args):
        self._compare_tariffs()

    def get_config(self, item, default=None):
        if item in self.config_state:
            return self._value_from_state(self.config_state[item])

        if item in self.config:
            if isinstance(self.config[item], str) and self.entity_exists(self.config[item]):
                x = self.get_ha_value(self.config[item])
                return x
            elif isinstance(self.config[item], list):
                if min([isinstance(x, str)] for x in self.config[item])[0]:
                    if min([self.entity_exists(e) for e in self.config[item]]):
                        l = [self.get_ha_value(e) for e in self.config[item]]
                        try:
                            return sum(l)
                        except:
                            return l
                else:
                    return self.config[item]
            else:
                return self.config[item]
        else:
            return default

    def _setup_schedule(self):
        start_opt = pd.Timestamp.now().ceil(f"{self.get_config('optimise_frequency_minutes')}min").to_pydatetime()
        self.timer_handle = self.run_every(
            self.optimise_time,
            start=start_opt,
            interval=self.get_config("optimise_frequency_minutes") * 60,
        )
        self.log(
            f"Optimiser will run every {self.get_config('optimise_frequency_minutes')} minutes from {start_opt.strftime('%H:%M %Z')} or on {EVENT_TRIGGER} Event"
        )

    def _load_contract(self):
        self.rlog("")
        self.rlog("Loading Contract:")
        self._status("Loading Tariffs")
        self.rlog("-----------------")
        self.tariff_codes = {}
        self.agile = False

        i = 0
        n = 5

        old_contract = self.contract
        self.contract = None

        while self.contract is None and i < n:
            if self.get_config("octopus_auto"):
                try:
                    self.rlog(f"Trying to auto detect Octopus tariffs:")

                    octopus_entities = [
                        name
                        for name in self.get_state_retry(BOTTLECAP_DAVE["domain"]).keys()
                        if ("octopus_energy_electricity" in name and BOTTLECAP_DAVE["rates"] in name)
                    ]

                    entities = {}
                    entities["import"] = [x for x in octopus_entities if not "export" in x]
                    entities["export"] = [x for x in octopus_entities if "export" in x]

                    for imp_exp in IMPEXP:
                        for entity in entities[imp_exp]:
                            tariff_code = self.get_state_retry(entity, attribute="all")["attributes"].get(
                                BOTTLECAP_DAVE["tariff_code"], None
                            )

                            self.rlog(f"  Found {imp_exp} entity {entity}: Tariff code: {tariff_code}")

                    tariffs = {x: None for x in IMPEXP}
                    for imp_exp in IMPEXP:
                        if self.debug:
                            self.log(f">>>{imp_exp}: {entities[imp_exp]}")
                        if len(entities[imp_exp]) > 0:
                            for entity in entities[imp_exp]:
                                tariff_code = self.get_state_retry(entity, attribute="all")["attributes"].get(
                                    BOTTLECAP_DAVE["tariff_code"], None
                                )
                                if self.debug:
                                    self.log(f">>> {tariff_code}")

                                if tariff_code is not None:
                                    tariffs[imp_exp] = pv.Tariff(
                                        tariff_code,
                                        export=(imp_exp == "export"),
                                        host=self,
                                    )
                                    self.bottlecap_entities[imp_exp] = entity
                                    if "AGILE" in tariff_code:
                                        self.agile = True

                    self.contract = pv.Contract(
                        "current",
                        imp=tariffs["import"],
                        exp=tariffs["export"],
                        host=self,
                    )
                    self.log("")
                    self.rlog("Contract tariffs loaded OK")

                except Exception as e:
                    self.rlog(f"{e.__traceback__.tb_lineno}: {e}", level="ERROR")
                    self.rlog(
                        "Failed to find tariff from Octopus Energy Integration",
                        level="WARNING",
                    )
                    self.contract = None

            if self.contract is None:
                if ("octopus_account" in self.config) and ("octopus_api_key" in self.config):
                    if (self.config["octopus_account"] is not None) and (self.config["octopus_api_key"] is not None):
                        for x in ["octopus_account", "octopus_api_key"]:
                            if self.config[x] not in self.redact_regex:
                                self.redact_regex.append(x)
                                self.redact_regex.append(x.lower().replace("-", "_"))
                        try:
                            self.rlog(
                                f"Trying to load tariffs using Account: {self.config['octopus_account']} API Key: {self.config['octopus_api_key']}"
                            )
                            self.octopus_account = pv.OctopusAccount(
                                self.config["octopus_account"],
                                self.config["octopus_api_key"],
                            )

                            self.contract = pv.Contract(
                                "current",
                                octopus_account=self.octopus_account,
                                host=self,
                            )

                            self.rlog(
                                "Tariffs loaded using Octopus Account details from API Key",
                                level="WARNING",
                            )

                        except Exception as e:
                            self.rlog(e, level="ERROR")
                            self.rlog(
                                f"Unable to load Octopus Account details using API Key: {e} Trying other methods.",
                                level="WARNING",
                            )

            if self.contract is None:
                if (
                    "octopus_import_tariff_code" in self.config
                    and self.config["octopus_import_tariff_code"] is not None
                ):
                    try:
                        str = f"Trying to load tariff codes: Import: {self.config['octopus_import_tariff_code']}"

                        if "octopus_export_tariff_code" in self.config:
                            str += f" Export: {self.config['octopus_export_tariff_code']}"
                        self.rlog(str)

                        tariffs = {x: None for x in IMPEXP}
                        for imp_exp in IMPEXP:
                            if f"octopus_{imp_exp}_tariff_code" in self.config:
                                tariffs[imp_exp] = pv.Tariff(
                                    self.config[f"octopus_{imp_exp}_tariff_code"],
                                    export=(imp_exp == "export"),
                                    host=self,
                                )

                        self.contract = pv.Contract(
                            "current",
                            imp=tariffs["import"],
                            exp=tariffs["export"],
                            host=self,
                        )
                        self.rlog("Contract tariffs loaded OK from Tariff Codes")
                    except Exception as e:
                        self.rlog(f"Unable to load Tariff Codes {e}", level="ERROR")

            if self.contract is None:
                i += 1
                self.rlog(f"Failed to load contact - Attempt {i} of {n}. Waiting 2 minutes to re-try")
                time.sleep(12)

        if self.contract is None:
            e = f"Failed to load contract in {n} attempts. FATAL ERROR"
            self.rlog(e)
            if old_contract is None:
                raise ValueError(e)
            else:
                self.log("Reverting to previous contract", level="ERROR")
                self.contract = old_contract

        else:
            if self.contract.tariffs["export"] is None:
                self.contract.tariffs["export"] = pv.Tariff("None", export=True, unit=0, octopus=False, host=self)

            self.rlog("")
            self._load_saving_events()
            self._check_for_io()

        self.rlog("Finished loading contract")

    def _check_tariffs(self):
        if self.bottlecap_entities["import"] is not None:
            self._check_tariffs_vs_bottlecap()

        self.log("")
        self.log("Checking tariff start and end times:")
        self.log("------------------------------------")
        tariff_error = False
        for direction in self.contract.tariffs:
            # for imp_exp, t in zip(IMPEXP, [self.contract.imp, self.contract.exp]):
            tariff = self.contract.tariffs[direction]
            if tariff is not None:
                try:
                    z = tariff.end().strftime(DATE_TIME_FORMAT_LONG)
                    if tariff.end() < pd.Timestamp.now(tz="UTC"):
                        z = z + " <<< ERROR: Tariff end datetime in past"
                        tariff_error = True

                except:
                    z = "N/A"

                if tariff.start() > pd.Timestamp.now(tz="UTC"):
                    z = z + " <<< ERROR: Tariff start datetime in future"
                    tariff_error = True

                self.log(
                    f"  {direction.title()}: {tariff.name:40s} Start: {tariff.start().strftime(DATE_TIME_FORMAT_LONG)} End: {z} "
                )
                if "AGILE" in tariff.name:
                    self.agile = True

        if self.agile:
            self.log("  AGILE tariff detected. Rates will update at 16:00 daily")

    def _load_saving_events(self):
        if (
            len([name for name in self.get_state_retry("event").keys() if ("octoplus_saving_session_events" in name)])
            > 0
        ):
            saving_events_entity = [
                name for name in self.get_state_retry("event").keys() if ("octoplus_saving_session_events" in name)
            ][0]
            self.log("")
            self.rlog(f"Found Octopus Savings Events entity: {saving_events_entity}")
            octopus_account = self.get_state_retry(entity_id=saving_events_entity, attribute="account_id")

            self.config["octopus_account"] = octopus_account
            if octopus_account not in self.redact_regex:
                self.redact_regex.append(octopus_account)
                self.redact_regex.append(octopus_account.lower().replace("-", "_"))

            available_events = self.get_state_retry(saving_events_entity, attribute="all")["attributes"][
                "available_events"
            ]

            if len(available_events) > 0:
                self.log("Joining the following new Octoplus Events:")
                for event in available_events:
                    if event["id"] not in self.saving_events:
                        self.saving_events[event["id"]] = event
                        self.log(
                            f"{event['id']:8d}: {pd.Timestamp(event['start']).strftime(DATE_TIME_FORMAT_SHORT)} - {pd.Timestamp(event['end']).strftime(DATE_TIME_FORMAT_SHORT)} at {int(event['octopoints_per_kwh'])/8:5.1f}p/kWh"
                        )
                        self.call_service(
                            "octopus_energy/join_octoplus_saving_session_event",
                            entity_id=saving_events_entity,
                            event_code=event["code"],
                        )

            joined_events = self.get_state_retry(saving_events_entity, attribute="all")["attributes"]["joined_events"]

            for event in joined_events:
                if event["id"] not in self.saving_events and pd.Timestamp(event["end"], tz="UTC") > pd.Timestamp.now(
                    tz="UTC"
                ):
                    self.saving_events[event["id"]] = event

        self.log("")
        if len(self.saving_events) > 0:
            self.log("The following Octopus Saving Events have been joined:")
            for id in self.saving_events:
                self.log(
                    f"{id:8d}: {pd.Timestamp(self.saving_events[id]['start']).strftime(DATE_TIME_FORMAT_SHORT)} - {pd.Timestamp(self.saving_events[id]['end']).strftime(DATE_TIME_FORMAT_SHORT)} at {int(self.saving_events[id]['octopoints_per_kwh'])/8:5.1f}p/kWh"
                )
        else:
            self.log("No upcoming Octopus Saving Events detected or joined:")

    def get_ha_value(self, entity_id):
        value = None

        # if the entity doesn't exist return None
        if self.entity_exists(entity_id=entity_id):
            state = self.get_state_retry(entity_id=entity_id)

            # if the state is None return None
            if state is not None:
                if (state in ["unknown", "unavailable"]) and (entity_id[:6] != "button"):
                    e = f"HA returned {state} for state of {entity_id}"
                    self._status(f"ERROR: {e}")
                    self.log(e, level="ERROR")
                # if the state is 'on' or 'off' then it's a bool
                elif state.lower() in ["on", "off", "true", "false"]:
                    value = state.lower() in ["on", "true"]

                # see if we can coerce it into an int 1st and then a floar
                else:
                    for t in [int, float]:
                        try:
                            value = t(state)
                        except:
                            pass

                # if none of the above return a string
                if value is None:
                    value = state

        return value

    def get_default_config(self, item):
        if item in DEFAULT_CONFIG:
            return DEFAULT_CONFIG[item]["default"]
        if item in self.inverter.config:
            return self.inverter.config[item]
        if item in self.inverter.brand_config:
            return self.inverter.brand_config[item]
        else:
            return None

    def same_type(self, a, b):
        if type(a) != type(b):
            (isinstance(a, int) | isinstance(a, float)) & (isinstance(b, int) | isinstance(b, float))
        else:
            return True

    def _load_args(self, items=None):
        if self.debug:
            self.rlog(self.args)

        self.prefix = self.args.get("prefix", "solis")

        self._status("Loading Configuation")
        over_write = self.args.get("overwrite_ha_on_restart", True)

        change_entities = []
        self.yaml_config = {}

        self.rlog("Reading arguments from YAML:")
        self.rlog("-----------------------------------")
        if over_write:
            self.rlog("")
            self.rlog("  Over-write flag is set so YAML will over-write HA")

        if items is None:
            items = [i for i in self.args if i not in SYSTEM_ARGS]

        for item in items:
            # Attempt to read entity states for all string paramters unless they start
            # with"id_":
            if not isinstance(self.args[item], list):
                self.args[item] = [self.args[item]]

            values = [
                (v.replace("{device_name}", self.device_name) if isinstance(v, str) else v) for v in self.args[item]
            ]

            if values[0] is None:
                self.config[item] = self.get_default_config(item)
                self.rlog(
                    f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: system default. Null entry found in YAML.",
                    level="WARNING",
                )

            # if the item starts with 'id_' then it must be an entity that exists:
            elif item == "alt_tariffs":
                self.config[item] = values
                for i, x in enumerate(values):
                    if i == 0:
                        str1 = item
                        str2 = "="
                    else:
                        str1 = ""
                        str2 = " "

                    self.rlog(f"    {str1:34s} {str2} {x['name']:27s} Import: {x['octopus_import_tariff_code']:>36s}")
                    self.rlog(f"    {'':34s}   {'':27s} Export: {x['octopus_export_tariff_code']:>36s}")
                self.yaml_config[item] = self.config[item]

            elif "id_" in item:
                if min([self.entity_exists(v) for v in values]):
                    if len(values) == 1:
                        self.config[item] = values[0]
                    else:
                        self.config[item] = values

                    self.rlog(
                        f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: value(s) in YAML"
                    )
                    self.yaml_config[item] = self.config[item]

                elif self.entity_exists(self.get_default_config(item)):
                    self.config[item] = self.get_default_config(item)
                    self.rlog(
                        f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: system default. Entities listed in YAML {values} do not all exist in HA.",
                        level="WARNING",
                    )
                else:
                    e = f"    {item:34s} : Neither the entities listed in the YAML {values[0]} nor the system default of {self.get_default_config(item)} exist in HA."
                    self.rlog(e, level="ERROR")
                    raise ValueError(e)

            else:
                # The value should be read explicitly
                if self.debug:
                    self.rlog(f"{item}:")
                    for value in self.args[item]:
                        self.rlog(f"\t{value}")

                arg_types = {t: [isinstance(v, t) for v in values] for t in [str, float, int, bool]}

                if (
                    len(values) == 1
                    and isinstance(values[0], str)
                    and (pd.to_datetime(values[0], errors="coerce", format="%H:%M") != pd.NaT)
                ):
                    self.config[item] = values[0]
                    self.rlog(
                        f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: value in YAML"
                    )
                    self.yaml_config[item] = self.config[item]

                elif min(arg_types[str]):
                    if self.debug:
                        self.rlog("\tFound a valid list of strings")

                    if isinstance(self.get_default_config(item), str) and len(values) == 1:
                        self.config[item] = values[0]
                        self.rlog(
                            f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: value in YAML"
                        )
                        self.yaml_config[item] = self.config[item]

                    else:
                        ha_values = [self.get_ha_value(entity_id=v) for v in values]
                        val_types = {
                            t: np.array([isinstance(v, t) for v in ha_values]) for t in [str, float, int, bool]
                        }
                        # if they are all float or int

                        valid_strings = [
                            j
                            for j in [h for h in zip(ha_values[:-1], values[:-1]) if h[0]]
                            if j[0] in DEFAULT_CONFIG[item]["options"]
                        ]

                        if np.min(val_types[int] | val_types[float]):
                            self.config[item] = values
                            self.rlog(
                                f"    {item:34s} = {str(sum(ha_values)):57s} {str(self.get_config(item)):>6s}: HA entities listed in YAML"
                            )
                        # if any of list but the last one are strings and the default for the item is a string
                        # try getting values from all the entities
                        elif valid_strings:
                            self.config[item] = valid_strings[0][0]
                            if not "sensor" in valid_strings[0][1]:
                                self.change_items[valid_strings[0][1]] = item
                            self.rlog(
                                f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: HA entities listed in YAML"
                            )

                        elif len(values) > 1:
                            if self.same_type(values[-1], self.get_default_config(item)):
                                self.config[item] = values[-1]
                                self.rlog(
                                    f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: YAML default. Unable to read from HA entities listed in YAML."
                                )

                            elif values[-1] in self.get_default_config(item):
                                self.rlog(values)
                                self.config[item] = values[-1]
                                self.rlog(
                                    f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: YAML default. Unable to read from HA entities listed in YAML."
                                )
                        else:
                            if item in DEFAULT_CONFIG:
                                self.config[item] = self.get_default_config(item)

                                self.rlog(
                                    f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: system default. Unable to read from HA entities listed in YAML. No default in YAML.",
                                    level="WARNING",
                                )
                            elif item in self.inverter.config or item in self.inverter.brand_config:
                                self.config[item] = self.get_default_config(item)

                                self.rlog(
                                    f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: inverter brand default. Unable to read from HA entities listed in YAML. No default in YAML.",
                                    level="WARNING",
                                )
                            else:
                                self.config[item] = values[0]
                                self.rlog(
                                    f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: YAML default value. No default defined."
                                )

                elif len(values) == 1 and (arg_types[bool][0] or arg_types[int][0] or arg_types[float][0]):
                    if self.debug:
                        self.rlog("\tFound a single default value")

                    self.config[item] = values[0]
                    self.rlog(
                        f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: value in YAML"
                    )
                    self.yaml_config[item] = self.config[item]

                elif (
                    len(values) > 1
                    and (min(arg_types[str][:-1]))
                    and (arg_types[bool][-1] or arg_types[int][-1] or arg_types[float][-1])
                ):
                    if self.debug:
                        self.rlog("\tFound a valid list of strings followed by a single default value")
                    ha_values = [self.get_ha_value(entity_id=v) for v in values[:-1]]
                    val_types = {t: np.array([isinstance(v, t) for v in ha_values]) for t in [str, float, int, bool]}
                    # if they are all float or int
                    if np.min(val_types[int] | val_types[float]):
                        self.config[item] = sum(ha_values)
                        self.rlog(
                            f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: HA entities listed in YAML"
                        )
                        # If these change then we need to trigger automatically
                        for v in values[:-1]:
                            if not "sensor" in v:
                                self.change_items[v] = item

                    else:
                        self.config[item] = values[-1]
                        self.rlog(
                            f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: YAML default. Unable to read from HA entities listed in YAML."
                        )

                else:
                    self.config[item] = self.get_default_config(item)
                    self.rlog(
                        f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: system default. Invalid arguments in YAML.",
                        level="ERROR",
                    )

        self.rlog("")
        self.rlog("Checking config:")
        self.rlog("-----------------------")
        items_not_defined = (
            [i for i in DEFAULT_CONFIG if i not in self.config]
            + [i for i in self.inverter.config if i not in self.config]
            + [i for i in self.inverter.brand_config if i not in self.config]
        )

        if len(items_not_defined) > 0:
            for item in items_not_defined:
                self.config[item] = self.get_default_config(item)
                self.rlog(
                    f"    {item:34s} = {str(self.config[item]):57s} {str(self.get_config(item)):>6s}: system default. Not in YAML.",
                    level="WARNING",
                )
        else:
            self.rlog("All config items defined OK")

        self.rlog("")

        self._expose_configs(over_write)

    def _name_from_item(self, item):
        name = item.replace("_", " ")
        for word in name.split():
            name = name.replace(word, word.title())
        return f"{self.prefix.title()} {name}"

    def _state_from_value(self, value):
        if isinstance(value, bool):
            if value:
                state = "on"
            else:
                state = "off"
        elif isinstance(value, list):
            state = value[0]
        else:
            state = value
        return state

    def _expose_configs(self, over_write=True):
        mqtt_items = [
            item
            for item in DEFAULT_CONFIG
            if (item not in [self.change_items[entity] for entity in self.change_items])
            and ("id_" not in item)
            and ("json_" not in item)
            and ("alt_" not in item)
            and ("auto" not in item)
            and "domain" in DEFAULT_CONFIG[item]
        ]

        over_write_log = False

        for item in mqtt_items:
            state = None
            domain = DEFAULT_CONFIG[item]["domain"]
            id = f"{self.prefix.lower()}_{item}"
            entity_id = f"{domain}.{id}"
            attributes = DEFAULT_CONFIG[item].get("attributes", {})

            command_topic = f"homeassistant/{domain}/{id}/set"
            state_topic = f"homeassistant/{domain}/{id}/state"

            if not self.entity_exists(entity_id=entity_id):
                self.log(f"  - Creating HA Entity {entity_id} for {item} using MQTT Discovery")
                conf = (
                    {
                        "state_topic": state_topic,
                        "command_topic": command_topic,
                        "name": self._name_from_item(item),
                        "optimistic": True,
                        "object_id": id,
                        "unique_id": id,
                    }
                    | attributes
                    | MQTT_CONFIGS.get(domain, {})
                )

                conf_topic = f"homeassistant/{domain}/{id}/config"
                self.mqtt.mqtt_publish(conf_topic, dumps(conf), retain=True)
                state = self._state_from_value(self.config[item])
                if domain == "switch":
                    self.mqtt.mqtt_publish(command_topic, state.upper(), retain=True)
                    self.mqtt.mqtt_publish(state_topic, state.upper(), retain=True)
                else:
                    self.mqtt.mqtt_publish(state_topic, state, retain=True)
                    self.mqtt.mqtt_publish(command_topic, state, retain=True)

                self.mqtt.mqtt_subscribe(state_topic)

            elif (
                isinstance(self.get_ha_value(entity_id), str)
                and (self.get_ha_value(entity_id) not in attributes.get("options", {}))
                and (domain not in ["text", "button"])
            ):

                state = self._state_from_value(self.get_default_config(item))

                self.log(f"  - Found unexpected str for {entity_id} reverting to default of {state}")

                self.set_state(state=state, entity_id=entity_id)

            elif item in self.yaml_config:
                state = self.get_state_retry(entity_id)
                new_state = str(self._state_from_value(self.config[item]))
                if over_write and state != new_state:
                    if not over_write_log:
                        self.log("")
                        self.log("Over-writing HA from YAML:")
                        self.log("--------------------------")
                        self.log("")
                        self.log(f"  {'Config Item':40s}  {'HA Entity':42s}  Old State   New State")
                        self.log(f"  {'-----------':40s}  {'---------':42s}  ----------  ----------")
                        over_write_log = True

                    str_log = f"  {item:40s}  {entity_id:42s}  {state:10s}  {new_state:10s}"
                    over_write_count = 0
                    while (state != new_state) and (over_write_count < OVERWRITE_ATTEMPTS):
                        self.set_state(state=new_state, entity_id=entity_id)
                        time.sleep(0.1)
                        state = self.get_state_retry(entity_id)
                        over_write_count += 1

                    if state == new_state:
                        self.log(f"{str_log} OK")
                    else:
                        self.log(f"{str_log} <<< FAILED!", level="WARN")

            else:
                state = self.get_state_retry(entity_id)

            self.config[item] = entity_id
            self.change_items[entity_id] = item
            self.config_state[item] = state

        self.log("")
        self.log("Syncing config with Home Assistant:")
        self.log("-----------------------------------")

        if self.change_items:
            self.log("")
            self.log(f"  {'Config Item':40s}  {'HA Entity':42s}  Current State")
            self.log(f"  {'-----------':40s}  {'---------':42s}  -------------")

            self.ha_entities = {}
            for entity_id in self.change_items:
                if not "sensor" in entity_id:
                    item = self.change_items[entity_id]
                    self.log(f"  {item:40s}  {entity_id:42s}  {self.config_state[item]}")
                    self.handles[entity_id] = self.listen_state(
                        callback=self.optimise_state_change, entity_id=entity_id
                    )
                    self.ha_entities[item] = entity_id

        self.mqtt.listen_state(
            callback=self.optimise_state_change,
        )

    def _status(self, status):
        entity_id = f"sensor.{self.prefix.lower()}_status"
        attributes = {"last_updated": pd.Timestamp.now().strftime(DATE_TIME_FORMAT_LONG)}
        self.set_state(state=status, entity_id=entity_id, attributes=attributes)

    @ad.app_lock
    def optimise_state_change(self, entity_id, attribute, old, new, kwargs):
        item = self.change_items[entity_id]
        self.log(f"State change detected for {entity_id} [config item: {item}] from {old} to {new}:")

        self.config_state[item] = new

        if "forced" in item:
            self._setup_schedule()

        if item in [
            "inverter_efficiency_percent",
            "inverter_power_watts",
            "inverter_loss_watts",
            "charger_efficiency_percent",
            "battery_capacity_wh",
            "maximum_dod_percent",
        ]:
            self._load_pv_system_model()

        if "test" not in item:
            self.optimise()
        elif "button" in item:
            self._run_test()

    def _value_from_state(self, state):
        value = None
        try:
            value = int(state)
        except:
            pass

        if value is None:
            try:
                value = float(state)
            except:
                pass

        if value is None:
            if state in ["on", "off"]:
                value = state == "on"

        if value is None:
            time_value = pd.to_datetime(state, errors="coerce", format="%H:%M")
            if time_value != pd.NaT:
                value = state

        if value is None:
            value = state

        return value

    @ad.app_lock
    def optimise_event(self, event_name, data, kwargs):
        self.log(f"Optimiser triggered by {event_name}")
        self.optimise()

    @ad.app_lock
    def optimise_time(self, cb_args):
        self.log(f"Optimiser triggered by Scheduler ")
        self.optimise()

    @ad.app_lock
    def optimise(self):
        # initialse a DataFrame to cover today and tomorrow at 30 minute frequency

        self.log("")
        self._load_saving_events()

        if self.io:
            self._get_io()

        if self.get_config("forced_discharge") and (self.get_config("supports_forced_discharge", True)):
            discharge_enable = "enabled"
        else:
            discharge_enable = "disabled"

        self.log("")
        self.log(f"Starting Opimisation with discharge {discharge_enable}")
        self.log(f"------------------------------------{len(discharge_enable)*'-'}")

        self.log("")
        self.log("Checking tariffs:")
        self.log("-----------------")

        if self.agile:
            if (self.contract.tariffs["import"].end().day == pd.Timestamp.now().day) and (
                pd.Timestamp.now().hour >= 16
            ):
                self.log(
                    f"Contract end day: {self.contract.tariffs['import'].end().day} Today:{pd.Timestamp.now().day}"
                )
                self._load_contract()

        elif pd.Timestamp.now(tz="UTC").hour == 0:
            self._load_contract()

        if self._check_tariffs():
            self.log("")
            self.log("  Tariff error detected. Attempting to re-load.")
            self.log("")
            self._load_contract()
        else:
            self.log("  Tariffs OK")
            self.log("")

        if self.io:
            self._get_io

        self.t0 = pd.Timestamp.now()
        self.static = pd.DataFrame(
            index=pd.date_range(
                pd.Timestamp.utcnow().normalize(),
                pd.Timestamp.utcnow().normalize() + pd.Timedelta(days=2),
                freq="30min",
                inclusive="left",
            ),
        )

        # Load Solcast
        solcast = self.load_solcast()

        if solcast is None:
            self.log("")
            self.log("Unable to optimise without Solcast data.", level="ERROR")
            return

        consumption = self.load_consumption(
            pd.Timestamp.utcnow().normalize(),
            pd.Timestamp.utcnow().normalize() + pd.Timedelta(days=2),
        )

        if consumption is None:
            self.log("")
            self.log("Unable to optimise without consumption data.", level="ERROR")
            return

        self.static = pd.concat([solcast, consumption], axis=1)
        self.time_now = pd.Timestamp.utcnow()

        self.static = self.static[self.time_now.floor("30min") :].fillna(0)
        # self.load_consumption()
        self.soc_now = self.get_config("id_battery_soc")
        x = self.hass2df(self.config["id_battery_soc"], days=1, log=self.debug)
        if self.debug:
            self.log(f">>> soc_now: {self.soc_now}")
            self.log(f">>> x: {x}")
            self.log(f">>> Original: {x.loc[x.loc[: self.static.index[0]].index[-1] :]}")

        try:
            self.soc_now = float(self.soc_now)

        except:
            self.log("")
            self.log("Unable to get current SOC from HASS. Using last value from History.", level="WARNING")
            self.soc_now = x.iloc[-1]

        # x = x.astype(float)
        x = pd.to_numeric(x, errors="coerce").interpolate()

        x = x.loc[x.loc[: self.static.index[0]].index[-1] :]
        if self.debug:
            self.log(f">>> Fixed   : {x.loc[x.loc[: self.static.index[0]].index[-1] :]}")

        x = pd.concat(
            [
                x,
                pd.Series(
                    data=[self.soc_now, nan],
                    index=[self.time_now, self.static.index[0]],
                ),
            ]
        ).sort_index()
        self.initial_soc = x.interpolate().loc[self.static.index[0]]
        if not isinstance(self.initial_soc, float):
            self.log("")
            self.log("Unable to optimise without initial SOC", level="ERROR")
            self._status("ERROR: No initial SOC")
            return

        self.log("")
        self.log(f"Initial SOC: {self.initial_soc}")

        self.flows = {
            "Base": self.pv_system.flows(
                self.initial_soc,
                self.static,
                solar="weighted",
            )
        }
        self.log("Calculating Base flows:")

        if len(self.flows["Base"]) == 0:
            self.log("")
            self.log("  Unable to calculate baseline perfoormance", level="ERROR")
            self._status("ERROR: Baseline performance")
            return

        self.optimised_cost = {"Base": self.contract.net_cost(self.flows["Base"])}

        self.log("")
        if self.get_config("use_solar", True):
            str_log = (
                f'Optimising for Solcast {self.get_config("solcast_confidence_level")}% confidence level forecast'
            )
        else:
            str_log = "Optimising without Solar"

        self.log(
            str_log
            + f" from {self.static.index[0].strftime(DATE_TIME_FORMAT_SHORT)} to {self.static.index[-1].strftime(DATE_TIME_FORMAT_SHORT)}"
        )

        cases = {
            "Optimised Charging": {
                "export": False,
                "discharge": False,
            },
            "Optimised PV Export": {
                "export": True,
                "discharge": False,
            },
            "Forced Discharge": {
                "export": True,
                "discharge": True,
            },
        }

        if not self.get_config("include_export"):
            self.selected_case = "Optimised Charging"
        elif not self.get_config("forced_discharge"):
            self.selected_case = "Optimised PV Export"
        else:
            self.selected_case = "Forced Discharge"

        self._status("Optimising charge plan")

        for case in cases:
            self.flows[case] = self.pv_system.optimised_force(
                self.initial_soc,
                self.static,
                self.contract,
                solar="weighted",
                export=cases[case]["export"],
                discharge=cases[case]["discharge"],
                log=(case == self.selected_case),
                max_iters=MAX_ITERS,
            )

            self.optimised_cost[case] = self.contract.net_cost(self.flows[case])

        self.ulog("Optimisation Summary")
        self.log(f"  {'Base cost:':40s} {self.optimised_cost['Base'].sum():6.1f}p")
        for case in cases:
            str_log = f"  {f'Optimised cost ({case}):':40s} {self.optimised_cost[case].sum():6.1f}p"
            if case == self.selected_case:
                str_log += " <=== Current Setup"
            self.log(str_log)

        # self.opt = self.pv_system.optimised_force(
        #     self.initial_soc,
        #     self.static,
        #     self.contract,
        #     solar="weighted",
        #     export=self.get_config("use_export"),
        #     discharge=self.get_config("forced_discharge"),
        # )
        # self.opt_cost = self.optimised_cost[selected_case]

        self.opt = self.flows[self.selected_case]

        self.log("")

        self._create_windows()

        self.log("")
        self.log(
            f"Plan time: {self.static.index[0].strftime('%d-%b %H:%M')} - {self.static.index[-1].strftime('%d-%b %H:%M')} Initial SOC: {self.initial_soc} Base Cost: {self.optimised_cost['Base'].sum():5.1f} Opt Cost: {self.optimised_cost[self.selected_case].sum():5.1f}"
        )
        self.log("")
        optimiser_elapsed = round((pd.Timestamp.now() - self.t0).total_seconds(), 1)
        self.log(f"Optimiser elapsed time {optimiser_elapsed:0.1f} seconds")
        self.log("")
        self.log("")
        self.write_to_hass(
            entity=f"sensor.{self.prefix}_optimiser_elapsed",
            state=optimiser_elapsed,
            attributes={
                "state_class": "measurement",
                "state_class": "duration",
                "unit_of_measurement": "s",
            },
        )

        self._status("Writing to HA")
        self._write_output()

        if self.get_config("read_only"):
            self.log("Read only mode enabled. Not querying inverter.")
            self._status("Idle (Read Only)")

        else:
            # Get the current status of the inverter
            did_something = True
            self._status("Updating Inverter")

            inverter_update_count = 0
            while did_something and inverter_update_count < MAX_INVERTER_UPDATES:
                inverter_update_count += 1

                status = self.inverter.status
                self._log_inverter_status(status)

                time_to_slot_start = (self.charge_start_datetime - pd.Timestamp.now(self.tz)).total_seconds() / 60
                time_to_slot_end = (self.charge_end_datetime - pd.Timestamp.now(self.tz)).total_seconds() / 60

                # if len(self.windows) > 0:
                if (
                    (time_to_slot_start > 0)
                    and (time_to_slot_start < self.get_config("optimise_frequency_minutes"))
                    and (len(self.windows) > 0)
                ):
                    # Next slot starts before the next optimiser run. This implies we are not currently in
                    # a charge or discharge slot

                    if len(self.windows) > 0:
                        self.log(f"Next charge/discharge window starts in {time_to_slot_start:0.1f} minutes.")
                    else:
                        self.log("No charge/discharge windows planned.")

                    if self.charge_power > 0:
                        self.inverter.control_discharge(enable=False)

                        self.inverter.control_charge(
                            enable=True,
                            start=self.charge_start_datetime,
                            end=self.charge_end_datetime,
                            power=self.charge_power,
                            target_soc=self.charge_target_soc,
                        )


                    elif self.charge_power < 0:
                        self.inverter.control_charge(enable=False)

                        self.inverter.control_discharge(
                            enable=True,
                            start=self.charge_start_datetime,
                            end=self.charge_end_datetime,
                            power=self.charge_power,
                            target_soc=self.charge_target_soc,
                        )

                elif (
                    (time_to_slot_start <= 0)
                    and (time_to_slot_start < self.get_config("optimise_frequency_minutes"))
                    and (len(self.windows) > 0)
                ):
                    # We are currently in a charge/discharge slot

                    # If the current slot is a Hold SOC slot and we aren't holding then we need to
                    # enable Hold SOC
                    if self.hold and self.hold[0]["active"]:
                        if not status["hold_soc"]["active"] or status["hold_soc"]["soc"] != self.hold[0]["soc"]:
                            self.log(f"  Enabling SOC hold at SOC of {self.hold[0]['soc']:0.0f}%")
                            self.inverter.hold_soc(
                                enable=True,
                                soc=self.hold[0]["soc"],
                                start=self.charge_start_datetime,
                                end=self.charge_end_datetime,
                            )
                        else:
                            self.log(f"  Inverter already holding SOC of {self.hold[0]['soc']:0.0f}%")

                    else:
                        self.log(f"Current charge/discharge window ends in {time_to_slot_end:0.1f} minutes.")

                        if self.charge_power > 0:
                            if not status["charge"]["active"]:
                                start = pd.Timestamp.now(tz=self.tz)
                            else:
                                start = None

                            if status["discharge"]["active"]:
                                self.inverter.control_discharge(
                                    enable=False,
                                )

                            self.inverter.control_charge(
                                enable=True,
                                start=start,
                                end=self.charge_end_datetime,
                                power=self.charge_power,
                                target_soc=self.charge_target_soc,
                            )


                        elif self.charge_power < 0:
                            if not status["discharge"]["active"]:
                                start = pd.Timestamp.now(tz=self.tz)
                            else:
                                start = None

                            if status["charge"]["active"]:
                                self.inverter.control_charge(
                                    enable=False,
                                )

                            self.inverter.control_discharge(
                                enable=True,
                                start=start,
                                end=self.charge_end_datetime,
                                power=self.charge_power,
                                target_soc=self.charge_target_soc,
                            )

                else:
                    if self.charge_power > 0:
                        direction = "charge"
                    elif self.charge_power < 0:
                        direction = "discharge"
                    else:
                        direction = "hold"

                    # We aren't in a charge/discharge slot and the next one doesn't start before the
                    # optimiser runs again

                    if len(self.windows) > 0:
                        str_log = f"Next {direction} window starts in {time_to_slot_start:0.1f} minutes "

                    else:
                        str_log = "No charge/discharge windows planned "

                    # If the next slot isn't soon then just check that current status matches what we see:
                    did_something = False

                    if status["charge"]["active"]:
                        str_log += " but inverter is charging. Disabling charge."
                        self.log(str_log)
                        self.inverter.control_charge(enable=False)
                        did_something = True

                    elif status["charge"]["start"] != status["charge"]["end"]:
                        str_log += " but charge start and end times are different."
                        self.log(str_log)
                        self.inverter.control_charge(enable=False)
                        did_something = True

                    if status["discharge"]["active"]:
                        str_log += " but inverter is discharging. Disabling discharge."
                        self.log(str_log)
                        self.inverter.control_discharge(enable=False)
                        did_something = True

                    elif status["discharge"]["start"] != status["discharge"]["end"]:
                        str_log += " but charge start and end times are different."
                        self.log(str_log)
                        self.inverter.control_charge(enable=False)
                        did_something = True

                    if len(self.windows) > 0:
                        if (
                            direction == "charge"
                            and self.charge_start_datetime > status["discharge"]["start"]
                            and status["discharge"]["start"] != status["discharge"]["end"]
                        ):
                            str_log += " but inverter has a discharge slot before then. Disabling discharge."
                            self.log(str_log)
                            self.inverter.control_discharge(enable=False)
                            did_something = True

                        elif (
                            direction == "discharge"
                            and self.charge_start_datetime > status["charge"]["start"]
                            and status["charge"]["start"] != status["charge"]["end"]
                        ):
                            str_log += " but inverter is has a charge slot before then. Disabling charge."
                            self.log(str_log)
                            self.inverter.control_charge(enable=False)
                            did_something = True

                    if status["hold_soc"]["active"]:
                        self.inverter.hold_soc(enable=False)
                        str_log += " but inverter is holding SOC. Disabling."
                        self.log(str_log)
                        did_something = True

                    if not did_something:
                        str_log += ". Nothing to do."
                        self.log(str_log)

                if did_something:
                    if self.get_config("update_cycle_seconds") is not None:
                        i = int(self.get_config("update_cycle_seconds") * 1.2)
                        self.log(f"Waiting for inverter Read cycle: {i} seconds")
                        while i > 0:
                            self._status(f"Waiting for inverter Read cycle: {i}")
                            time.sleep(1)
                            i -= 1

                        # status = self.inverter.status
                        # self._log_inverter_status(status)

            status_switches = {
                "charge": "off",
                "discharge": "off",
                "hold_soc": "off",
            }

            if status["hold_soc"]["active"]:
                self._status(f"Holding SOC at {status['hold_soc']['soc']:0.0f}%")
                status_switches["hold_soc"] = "on"

            elif status["charge"]["active"]:
                self._status("Charging")
                status_switches["charge"] = "on"

            elif status["discharge"]["active"]:
                self._status("Discharging")
                status_switches["discharge"] = "on"

            else:
                self._status("Idle")

            for switch in status_switches:
                service = f"switch/turn_{status_switches[switch]}"
                entity_id = f"switch.{self.prefix}_{switch}_active"
                self.call_service(
                    service=service,
                    entity_id=entity_id,
                )

    def _create_windows(self):
        self.opt["period"] = (self.opt["forced"].diff() > 0).cumsum()
        if (self.opt["forced"] != 0).sum() > 0:
            x = self.opt[self.opt["forced"] > 0].copy()
            x["start"] = x.index.tz_convert(self.tz)
            x["end"] = x.index.tz_convert(self.tz) + pd.Timedelta(30, "minutes")
            x["soc"] = x["soc"].round(0).astype(int)
            x["soc_end"] = x["soc_end"].round(0).astype(int)
            windows = pd.concat(
                [
                    x.groupby("period").first()[["start", "soc", "forced"]],
                    x.groupby("period").last()[["end", "soc_end"]],
                ],
                axis=1,
            )

            x = self.opt[self.opt["forced"] < 0].copy()
            x["start"] = x.index.tz_convert(self.tz)
            x["end"] = x.index.tz_convert(self.tz) + pd.Timedelta(30, "minutes")
            self.windows = pd.concat(
                [
                    x.groupby("period").first()[["start", "soc", "forced"]],
                    x.groupby("period").last()[["end", "soc_end"]],
                ],
                axis=1,
            )

            self.windows = pd.concat([windows, self.windows]).sort_values("start")
            tolerance = self.get_config("forced_power_group_tolerance")
            if tolerance > 0:
                self.windows["forced"] = ((self.windows["forced"] / tolerance).round(0) * tolerance).astype(int)

            self.windows["soc"] = self.windows["soc"].round(0).astype(int)
            self.windows["soc_end"] = self.windows["soc_end"].round(0).astype(int)

            self.windows["hold_soc"] = ""
            if self.config["supports_hold_soc"]:
                self.log("Checking for Hold SOC slots")
                self.windows.loc[
                    ((self.windows["soc_end"] - self.windows["soc"]).abs() < HOLD_TOLERANCE)
                    & (self.windows["soc"] > self.get_config("maximum_dod_percent")),
                    "hold_soc",
                ] = "<="

            self.log("")
            self.log("Optimal forced charge/discharge slots:")
            for window in self.windows.iterrows():
                self.log(
                    f"  {window[1]['start'].strftime('%d-%b %H:%M %Z'):>13s} - {window[1]['end'].strftime('%d-%b %H:%M %Z'):<13s}  Power: {window[1]['forced']:5.0f}W  SOC: {window[1]['soc']:4d}% -> {window[1]['soc_end']:4d}%  {window[1]['hold_soc']}"
                )

            self.charge_power = self.windows["forced"].iloc[0]
            self.charge_current = self.charge_power / self.get_config("battery_voltage", default=50)
            self.charge_start_datetime = self.windows["start"].iloc[0].tz_convert(self.tz)
            self.charge_end_datetime = self.windows["end"].iloc[0].tz_convert(self.tz)
            self.charge_target_soc = self.windows["soc_end"].iloc[0]
            self.hold = [
                {
                    "active": self.windows["hold_soc"].iloc[i] == "<=",
                    "soc": self.windows["soc_end"].iloc[i],
                }
                for i in range(0, min(len(self.windows), 1))
            ]

        else:
            self.log(f"No charging slots")
            self.charge_current = 0
            self.charge_power = 0
            self.charge_target_soc = 0
            self.charge_start_datetime = self.static.index[0].tz_convert(self.tz)
            self.charge_end_datetime = self.static.index[0].tz_convert(self.tz)
            self.hold = []
            self.windows = pd.DataFrame()

    def _log_inverter_status(self, status):
        self.log("")
        self.log(f"Current inverter status:")
        self.log("------------------------")
        for s in status:
            if not isinstance(status[s], dict):
                self.log(f"  {s:18s}: {status[s]}")
            else:
                self.log(f"  {s:18s}:")
                for x in status[s]:
                    if isinstance(status[s][x], pd.Timestamp):
                        self.log(f"    {x:16s}: {status[s][x].strftime(DATE_TIME_FORMAT_SHORT)}")
                    else:
                        self.log(f"    {x:16s}: {status[s][x]}")
        self.log("")

    def write_to_hass(self, entity, state, attributes={}):
        try:
            self.set_state(state=state, entity_id=entity, attributes=attributes)
            self.log(f"Output written to {entity}")

        except Exception as e:
            self.log(f"Couldn't write to entity {entity}: {e}")

    def write_cost(
        self,
        name,
        entity,
        cost,
        df,
    ):
        cost_today = self._cost_actual()
        midnight = pd.Timestamp.now(tz="UTC").normalize() + pd.Timedelta(24, "hours")
        df = df.fillna(0).round(2)
        df["period_start"] = df.index.tz_convert(self.tz).strftime("%Y-%m-%dT%H:%M:%S%z").str[:-2] + ":00"
        cols = [
            "soc",
            "forced",
            "import",
            "export",
            "grid",
            "consumption",
        ]

        cost = pd.DataFrame(pd.concat([cost_today, cost])).set_axis(["cost"], axis=1).fillna(0)
        cost["cumulative_cost"] = cost["cost"].cumsum()

        for d in [df, cost]:
            d["period_start"] = d.index.tz_convert(self.tz).strftime("%Y-%m-%dT%H:%M:%S%z").str[:-2] + ":00"

        state = round((cost["cost"].sum()) / 100, 2)

        attributes = (
            {
                "friendly_name": name,
                "device_class": "monetary",
                "state_class": "measurement",
                "unit_of_measurement": "GBP",
                "cost_today": round(
                    (cost["cost"].loc[: midnight - pd.Timedelta(30, "minutes")].sum()) / 100,
                    2,
                ),
                "cost_tomorrow": round((cost["cost"].loc[midnight:].sum()) / 100, 2),
            }
            | {col: df[["period_start", col]].to_dict("records") for col in cols if col in df.columns}
            | {"cost": cost[["period_start", "cumulative_cost"]].to_dict("records")}
        )

        self.write_to_hass(
            entity=entity,
            state=state,
            attributes=attributes,
        )

    def _write_output(self):
        if self.get_config("id_consumption_today") > 0:
            unit_cost_today = round(
                self._cost_actual().sum() / self.get_config("id_consumption_today"),
                1,
            )
        else:
            unit_cost_today = 0

        self.log(f"Average unit cost today: {unit_cost_today:0.2f}p/kWh")
        self.write_to_hass(
            entity=f"sensor.{self.prefix}_unit_cost_today",
            state=unit_cost_today,
            attributes={
                "friendly_name": "PV Opt Unit Electricity Cost Today",
                "unit_of_measurement": "p/kWh",
            },
        )

        self.write_cost(
            "PV Opt Base Cost",
            entity=f"sensor.{self.prefix}_base_cost",
            cost=self.optimised_cost["Base"],
            df=self.flows["Base"],
        )

        self.write_cost(
            "PV Opt Optimised Cost",
            entity=f"sensor.{self.prefix}_opt_cost",
            cost=self.optimised_cost[self.selected_case],
            df=self.flows[self.selected_case],
        )

        self.write_to_hass(
            entity=f"sensor.{self.prefix}_charge_start",
            state=self.charge_start_datetime,
            attributes={
                "friendly_name": "PV Opt Next Charge Period Start",
                "device_class": "timestamp",
                "windows": [
                    {
                        k: window[1][k]
                        for k in [
                            "start",
                            "end",
                            "forced",
                            "soc",
                            "soc_end",
                            "hold_soc",
                        ]
                    }
                    for window in self.windows.iterrows()
                ],
            },
        )

        self.write_to_hass(
            entity=f"sensor.{self.prefix}_charge_end",
            state=self.charge_end_datetime,
            attributes={
                "friendly_name": "PV Opt Next Charge Period End",
            },
        )

        self.write_to_hass(
            entity=f"sensor.{self.prefix}_charge_current",
            state=round(self.charge_current, 2),
            attributes={
                "friendly_name": "PV Opt Charging Current",
                "unit_of_measurement": "A",
                "state_class": "measurement",
                "device_class": "current",
            },
        )

        for offset in [1, 4, 8, 12]:
            loc = pd.Timestamp.now(tz="UTC") + pd.Timedelta(offset, "hours")
            locs = [loc.floor("30min"), loc.ceil("30min")]
            socs = [self.opt.loc[l]["soc"] for l in locs]
            soc = (loc - locs[0]) / (locs[1] - locs[0]) * (socs[1] - socs[0]) + socs[0]
            entity_id = f"sensor.{self.prefix}_soc_h{offset}"
            attributes = {
                "friendly_name": f"PV Opt Predicted SOC ({offset} hour delay)",
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "device_class": "battery",
            }
            self.write_to_hass(entity=entity_id, state=soc, attributes=attributes)

    def load_solcast(self):
        if not self.get_config("use_solar", True):
            df = pd.DataFrame(
                index=pd.date_range(pd.Timestamp.now(tz="UTC").normalize(), periods=96, freq="30min"),
                data={"Solcast": 0, "Solcast_p10": 0, "Solcast_p90": 0, "weighted": 0},
            )
            return df

        if self.debug:
            self.log("Getting Solcast data")
        try:
            solar = self.get_state_retry(self.config["id_solcast_today"], attribute="all")["attributes"][
                "detailedForecast"
            ]
            solar += self.get_state_retry(self.config["id_solcast_tomorrow"], attribute="all")["attributes"][
                "detailedForecast"
            ]

        except Exception as e:
            self.log(f"Failed to get solcast attributes: {e}")
            return

        try:
            # Convert to timestamps
            for s in solar:
                s["period_start"] = pd.Timestamp(s["period_start"])

            df = pd.DataFrame(solar)
            df = df.set_index("period_start")
            df.index = pd.to_datetime(df.index, utc=True)
            df = df.set_axis(["Solcast", "Solcast_p10", "Solcast_p90"], axis=1)

            confidence_level = self.get_config("solcast_confidence_level")
            weighting = {
                "Solcast_p10": max(50 - confidence_level, 0) / 40,
                "Solcast": 1 - abs(confidence_level - 50) / 40,
                "Solcast_p90": max(confidence_level - 50, 0) / 40,
            }

            df["weighted"] = 0
            for w in weighting:
                df["weighted"] += df[w] * weighting[w]

            df *= 1000
            df = df.fillna(0)
            # self.static = pd.concat([self.static, df], axis=1)
            self.log("Solcast forecast loaded OK")
            self.log("")
            return df

        except Exception as e:
            self.log(f"Error loading Solcast: {e}", level="ERROR")
            self.log("")
            return

    def _get_hass_power_from_daily_kwh(self, entity_id, start=None, end=None, days=None, log=False):
        if days is None:
            days = (pd.Timestamp.now(tz="UTC") - start).days + 1

        df = self.hass2df(
            entity_id,
            days=days,
            log=log,
        )

        if df is not None:
            df.index = pd.to_datetime(df.index)
            x = df.diff().clip(0).fillna(0).cumsum() + df.iloc[0]
            x.index = x.index.round("1s")
            y = -pd.concat([x.resample("1s").interpolate().resample("30min").asfreq(), x.iloc[-1:]]).diff(-1)
            dt = y.index.diff().total_seconds() / pd.Timedelta("60min").total_seconds() / 1000
            df = y[1:-1] / dt[2:]

            if start is not None:
                df = df.loc[start:]
            if end is not None:
                df = df.loc[:end]

        return df

    def load_consumption(self, start, end):
        self.log(
            f"Getting expected consumption data for {start.strftime(DATE_TIME_FORMAT_LONG)} to {end.strftime(DATE_TIME_FORMAT_LONG)}:"
        )

        time_now = pd.Timestamp.now(tz="UTC")
        if (start < time_now) and (end < time_now):
            self.log("  - Start and end are both in past so actuals will be used with no weighting")

        index = pd.date_range(start, end, inclusive="left", freq="30min")
        consumption = pd.DataFrame(index=index, data={"consumption": 0})
        df = None

        entity_ids = []
        entity_id = None

        if self.get_config("use_consumption_history"):
            days = int(self.get_config("consumption_history_days"))

            if "id_consumption" in self.config:
                entity_ids = self.config["id_consumption"]
                if not isinstance(entity_ids, list):
                    entity_ids = [entity_ids]

                entity_ids = [entity_id for entity_id in entity_ids if self.entity_exists(entity_id)]

            if (
                (len(entity_ids) == 0)
                and ("id_consumption_today" in self.config)
                and self.entity_exists(self.config["id_consumption_today"])
            ):
                entity_id = self.config["id_consumption_today"]

            if (start < time_now) and (end < time_now):
                for entity_id in entity_ids:
                    power = self.hass2df(entity_id=entity_id, days=days).loc[
                        start.floor("30min") : end.ceil("30min") + pd.Timedelta("30min")
                    ]

                    if power is not None:
                        power = self.riemann_avg(power)
                        consumption["consumption"] += power

                if consumption["consumption"].sum() == 0:
                    consumption["consumption"] = self._get_hass_power_from_daily_kwh(
                        entity_id,
                        start=start,
                        end=end,
                        log=self.debug,
                    )

                if consumption["consumption"].sum() == 0:
                    self._status("ERROR: No consumption history.")
                    return

            else:
                for entity_id in entity_ids:
                    power = self.hass2df(entity_id=entity_id, days=days)

                    power = self.riemann_avg(power)
                    if df is None:
                        df = power
                    else:
                        df += power

                if df is None:
                    self.log("Getting consumpo")
                    df = self._get_hass_power_from_daily_kwh(
                        entity_id,
                        days=days,
                        log=self.debug,
                    )

                if df is None:
                    self._status("ERROR: No consumption history.")
                    return

                actual_days = int(
                    round(
                        (df.index[-1] - df.index[0]).total_seconds() / 3600 / 24,
                        0,
                    )
                )

                self.log(
                    f"  - Got {actual_days} days history from {entity_id} from {df.index[0].strftime(DATE_TIME_FORMAT_SHORT)} to {df.index[-1].strftime(DATE_TIME_FORMAT_SHORT)}"
                )
                if int(actual_days) == days:
                    str_days = "OK"
                else:
                    self._status(f"WARNING: Consumption < {days} days.")
                    str_days = "Potential error. <<<"

                self.log(f"  - {days} days was expected. {str_days}")

                if len(self.zappi_entities) > 0:
                    zappi = self._get_zappi(days=days, log=True)

                df = df * (1 + self.get_config("consumption_margin") / 100)
                dfx = pd.Series(index=df.index, data=df.to_list())
                # Group by time and take the mean
                df = df.groupby(df.index.time).aggregate(self.get_config("consumption_grouping"))
                df.name = "consumption"

                if self.debug:
                    self.log(">>> All consumption:")
                    self.log(f">>> {dfx.to_string()}")
                    self.log(">>> Consumption grouped by time:")
                    self.log(f">>> {df}")

                temp = pd.DataFrame(index=index)
                temp["time"] = temp.index.time
                consumption_mean = temp.merge(df, "left", left_on="time", right_index=True)["consumption"]

                if days >= 7:
                    consumption_dow = self.get_config("day_of_week_weighting") * dfx.iloc[: len(temp)]
                    if len(consumption_dow) != len(consumption_mean):
                        self.log(">>> Inconsistent lengths in consumption arrays")
                        self.log(f">>> dow : {consumption_dow}")
                        self.log(f">>> mean: {consumption_mean}")

                    consumption["consumption"] += pd.Series(
                        consumption_dow.to_numpy()
                        + consumption_mean.to_numpy() * (1 - self.get_config("day_of_week_weighting")),
                        index=consumption_mean.index,
                    )
                else:
                    self.log(f"  - Ignoring 'Day of Week Weighting' because only {days} days of history is available")
                    consumption["consumption"] = consumption_mean

                self.log(f"  - Estimated consumption from {entity_id} loaded OK ")

        else:
            daily_kwh = self.get_config("daily_consumption_kwh")
            self.log(f"  - Creating consumption based on daily estimate of {daily_kwh} kWh")

            if self.get_config("shape_consumption_profile"):
                self.log("    and typical usage profile.")
                daily = (
                    pd.DataFrame(CONSUMPTION_SHAPE)
                    .set_index("hour")
                    .reindex(np.arange(0, 24.5, 0.5))
                    .interpolate()
                    .iloc[:-1]
                )
                daily["consumption"] *= daily_kwh / (daily["consumption"].sum() / 2000)
                daily.index = pd.to_datetime(daily.index, unit="h").time
                consumption["time"] = consumption.index.time
                consumption = pd.DataFrame(
                    consumption.merge(daily, left_on="time", right_index=True)["consumption_y"]
                ).set_axis(["consumption"], axis=1)
            else:
                self.log("    and flat usage profile.")
                consumption["consumption"] = self.get_config("daily_consumption_kwh") * 1000 / 24

            self.log("  - Consumption estimated OK")

        self.log(f"  - Total consumption: {(consumption['consumption'].sum() / 2000):0.1f} kWh")
        return consumption

    def _compare_tariffs(self):
        self.ulog("Comparing yesterday's tariffs")
        end = pd.Timestamp.now(tz="UTC").normalize()
        start = end - pd.Timedelta(24, "hours")

        solar = self._get_solar(start, end)
        if solar is None:
            self.log("  Unable to compare tariffs", level="ERROR")
            return

        consumption = self.load_consumption(start, end)
        static = pd.concat([solar, consumption], axis=1).set_axis(["solar", "consumption"], axis=1)

        initial_soc_df = self.hass2df(self.config["id_battery_soc"], days=2, freq="30min")
        initial_soc = initial_soc_df.loc[start]

        base = self.pv_system.flows(initial_soc, static, solar="solar")

        contracts = [self.contract]

        self.log("")
        self.log(f"Start:       {start.strftime(DATE_TIME_FORMAT_SHORT):>15s}")
        self.log(f"End:         {end.strftime(DATE_TIME_FORMAT_SHORT):>15s}")
        self.log(f"Initial SOC: {initial_soc:>15.1f}%")
        self.log(f"Consumption: {static['consumption'].sum()/2000:15.1f} kWh")
        self.log(f"Solar:       {static['solar'].sum()/2000:15.1f} kWh")

        if self.debug:
            self.log(f">>> Yesterday's data:\n{static.to_string()}")

        for tariff_set in self.config["alt_tariffs"]:
            code = {}
            tariffs = {}
            name = tariff_set["name"]
            for imp_exp in IMPEXP:
                code[imp_exp] = tariff_set[f"octopus_{imp_exp}_tariff_code"]
                tariffs[imp_exp] = pv.Tariff(code[imp_exp], export=(imp_exp == "export"), host=self)

            contracts.append(
                pv.Contract(
                    name=name,
                    imp=tariffs["import"],
                    exp=tariffs["export"],
                    host=self,
                )
            )

        actual = self._cost_actual(start=start, end=end - pd.Timedelta(30, "minutes"))
        static["period_start"] = static.index.tz_convert(self.tz).strftime("%Y-%m-%dT%H:%M:%S%z").str[:-2] + ":00"
        entity_id = f"sensor.{self.prefix}_opt_cost_actual"
        self.set_state(
            state=round(actual.sum() / 100, 2),
            entity_id=entity_id,
            attributes={
                "state_class": "measurement",
                "device_class": "monetary",
                "unit_of_measurement": "GBP",
                "friendly_name": f"PV Opt Comparison Actual",
            }
            | {col: static[["period_start", col]].to_dict("records") for col in ["solar", "consumption"]},
        )

        self.ulog("Net Cost comparison:", underline=None)
        self.log(f"  {'Tariff':20s}  {'Base Cost (GBP)':>20s}  {'Optimised Cost (GBP)':>20s} ")
        self.log(f"  {'------':20s}  {'---------------':>20s}  {'--------------------':>20s} ")
        self.log(f"  {'Actual':20s}  {'':20s}  {(actual.sum()/100):>20.3f}")

        cols = [
            "soc",
            "forced",
            "import",
            "export",
            "grid",
            "consumption",
            "solar",
        ]

        for contract in contracts:
            net_base = contract.net_cost(base, day_ahead=False)
            opt = self.pv_system.optimised_force(
                initial_soc,
                static,
                contract,
                solar="solar",
                export=True,
                discharge=True,
                max_iters=MAX_ITERS,
                log=False,
            )

            # opt["period_start"] = opt.index.tz_convert(self.tz).strftime("%Y-%m-%dT%H:%M:%S%z").str[:-2] + ":00"

            attributes = {
                "state_class": "measurement",
                "device_class": "monetary",
                "unit_of_measurement": "GBP",
                "friendly_name": f"PV Opt Comparison {contract.name}",
                "net_base": round(net_base.sum() / 100, 2),
                # } | {col: opt[["period_start", col]].to_dict("records") for col in cols if col in opt.columns}
            }

            net_opt = contract.net_cost(opt, day_ahead=False)
            self.log(f"  {contract.name:20s}  {(net_base.sum()/100):>20.3f}  {(net_opt.sum()/100):>20.3f}")
            entity_id = f"sensor.{self.prefix}_opt_cost_{contract.name}"
            self.set_state(
                state=round(net_opt.sum() / 100, 2),
                entity_id=entity_id,
                attributes=attributes,
            )

    def _get_solar(self, start, end):
        self.log(
            f"Getting yesterday's solar generation ({start.strftime(DATE_TIME_FORMAT_SHORT)} - {end.strftime(DATE_TIME_FORMAT_SHORT)}):"
        )
        # entity_id = self.config["id_daily_solar"]
        entity_id = self.config["id_solar_power"]
        if entity_id is None or not self.entity_exists(entity_id):
            return

        # dt = pd.date_range(
        #     start,
        #     end,
        #     freq="30min",
        # )

        days = (pd.Timestamp.now(tz="UTC") - start).days + 1
        # df = self.hass2df(entity_id, days=days).astype(float).resample("30min").ffill()

        df = self.hass2df(entity_id, days=days)
        if df is not None:

            df = (self.riemann_avg(df).loc[start : end - pd.Timedelta("30min")] / 10).round(0) * 10

        #     df.index = pd.to_datetime(df.index)
        #     self.log(f"  - {df.loc[dt[-2]]:0.1f} kWh")
        #     df = -df.loc[dt[0] : dt[-1]].diff(-1).clip(upper=0).iloc[:-1] * 2000
        #     self.log(f"\n{df.to_string()}")
        #     self.log(f"\n{df2.to_string()}")

        else:
            self.log("  - FAILED")
        self.log("")
        return df

    def _check_tariffs_vs_bottlecap(self):
        self.ulog("Checking tariff prices vs Octopus Energy Integration:")
        for direction in self.contract.tariffs:
            err = False
            if self.bottlecap_entities[direction] is None:
                str_log = "No OE Integration entity found."

            elif self.contract.tariffs[direction].name == "None":
                str_log = "No export tariff."

            else:
                df = pd.DataFrame(
                    self.get_state_retry(self.bottlecap_entities[direction], attribute=("rates"))
                ).set_index("start")["value_inc_vat"]
                df.index = pd.to_datetime(df.index)
                df *= 100
                df = pd.concat(
                    [
                        df,
                        self.contract.tariffs[direction].to_df(start=df.index[0], end=df.index[-1], day_ahead=False)[
                            "unit"
                        ],
                    ],
                    axis=1,
                ).set_axis(["bottlecap", "pv_opt"], axis=1)
                # self.log(df)

                # Drop any Savings Sessions

                for id in self.saving_events:
                    df = df.drop(df[self.saving_events[id]["start"] : self.saving_events[id]["end"]].index[:-1])

                pvopt_price = df["pv_opt"].mean()
                bottlecap_price = df["bottlecap"].mean()
                df["delta"] = df["pv_opt"] - df["bottlecap"]
                str_log = f"Average Prices - PV_OPT: {pvopt_price:5.2f} p/kWh  OE Integration: {bottlecap_price:5.2f} p/kWh  Mean difference: {df['delta'].abs().mean():5.2f} p/kWh"
                self.set_state(
                    entity_id=f"sensor.{self.prefix}_tariff_{direction}_OK",
                    state=round(df["delta"].abs().mean(), 2) == 0,
                )
                if round(df["delta"].abs().mean(), 2) > 0:
                    str_log += " <<< ERROR"
                    self._status("ERROR: Tariff inconsistency")
                    err = True

            self.log(f"  {direction.title()}: {str_log}")
            if err:
                self.rlog(self.contract.tariffs[direction].to_df(start=df.index[0], end=df.index[-1], day_ahead=False))

    def ulog(self, strlog, underline="-", words=False):
        self.log("")
        self.log(strlog)
        if underline is not None:
            if words:
                self.log(" ".join(["-" * len(word) for word in strlog.split()]))
            else:
                self.log(underline * len(strlog))

        self.log("")

    def _list_entities(self, domains=["select", "number", "sensor"]):
        domains = [d for d in domains if d in ["select", "number", "sensor"]]
        self.ulog(f"Available entities for device {self.device_name}:")
        for domain in domains:
            states = self.get_state_retry(domain)
            states = {k: states[k] for k in states if self.device_name in k}
            for entity_id in states:
                x = entity_id + f" ({states[entity_id]['attributes'].get('device_class',None)}):"
                x = f"  {x:60s}"

                if domain != "select":
                    x += f"{str(states[entity_id]['state']):>20s} {states[entity_id]['attributes'].get('unit_of_measurement','')}"

                self.log(x)

                if domain == "number":
                    x = "  - "
                    for attribute in DOMAIN_ATTRIBUTES[domain]:
                        x = f"{x} {attribute}: {states[entity_id]['attributes'][attribute]} "
                    self.rlog(x)
                elif domain == "select":
                    for option in states[entity_id]["attributes"]["options"]:
                        self.rlog(f"{option:>83s}")
        self.log("")

    def hass2df(self, entity_id, days=2, log=False, freq=None):
        if log:
            self.log(f">>> Getting {days} days' history for {entity_id}")
            self.log(f">>> Entity exits: {self.entity_exists(entity_id)}")

        hist = None

        i = 0
        while (hist is None) and (i < MAX_HASS_HISTORY_CALLS):
            hist = self.get_history(entity_id=entity_id, days=days)
            if hist is None:
                time.sleep(1)
            i += 1

        if (hist is not None) and (len(hist) > 0):
            df = pd.DataFrame(hist[0]).set_index("last_updated")["state"]
            df.index = pd.to_datetime(df.index, format="ISO8601")

            df = df.sort_index()
            df = df[df != "unavailable"]
            df = df[df != "unknown"]
            df = pd.to_numeric(df, errors="coerce")
            df = df.dropna()
            if isinstance(freq, str):
                try:
                    df = df.resample(freq).mean().interpolate()
                except:
                    pass

        else:
            self.log(f"No data returned from HASS entity {entity_id}", level="ERROR")
            df = None

        return df

    def write_and_poll_value(self, entity_id, value, tolerance=0.0, verbose=False):
        changed = False
        written = False
        state = float(self.get_state_retry(entity_id=entity_id))
        new_state = None
        diff = abs(state - value)
        if diff > tolerance:
            changed = True
            try:
                self.call_service("number/set_value", entity_id=entity_id, value=str(value))

                written = False
                retries = 0
                while not written and retries < WRITE_POLL_RETRIES:
                    retries += 1
                    time.sleep(WRITE_POLL_SLEEP)
                    new_state = float(self.get_state_retry(entity_id=entity_id))
                    written = new_state == value

            except:
                written = False

            if verbose:
                str_log = f"Entity: {entity_id:30s} Value: {float(value):4.1f}  Old State: {float(state):4.1f} "
                str_log += f"New state: {float(new_state):4.1f} Diff: {diff:4.1f} Tol: {tolerance:4.1f}"
                self.log(str_log)

        return (changed, written)

    def set_select(self, item, state):
        if state is not None:
            entity_id = self.config[f"id_{item}"]
            if self.get_state_retry(entity_id=entity_id) != state:
                self.call_service("select/select_option", entity_id=entity_id, option=state)
                self.rlog(f"Setting {entity_id} to {state}")

    def get_state_retry(self, *args, **kwargs):
        retries = 0
        state = None

        valid_state = False

        while not valid_state and retries < GET_STATE_RETRIES:
            state = self.get_state(*args, **kwargs)
            valid_state = (
                (("attribute" in kwargs) and (isinstance(state, dict)))
                or (state not in ["unknown", "unavailable", "", None, nan])
                or (len(args) == 1)
            )

            if not valid_state:
                retries += 1
                self.rlog(
                    f"  - Retrieved invalid state of {state} for {kwargs.get('entity_id', None)} (Attempt {retries} of {GET_STATE_RETRIES})",
                    level="WARNING",
                )
                time.sleep(GET_STATE_WAIT)

        if not valid_state:
            self.log("  - FAILED", level="ERROR")
            return None
        else:
            return state

    def riemann_avg(self, x, freq="30min"):
        dt = x.index.diff().total_seconds().fillna(0)

        integral = (dt * x.shift(1)).fillna(0).cumsum().resample(freq).last()
        avg = (integral.diff().shift(-1)[:-1] / pd.Timedelta(freq).total_seconds()).fillna(0).round(1)
        # self.log(avg)
        return avg


# %%
