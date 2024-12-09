# %%
import appdaemon.plugins.hass.hassapi as hass
import appdaemon.adbase as ad
import appdaemon.plugins.mqtt.mqttapi as mqtt
from json import dumps

import pandas as pd
import time
import math

import pvpy as pv
import numpy as np
from numpy import nan
from datetime import datetime, timedelta
import re

VERSION = "3.19.0-Beta-21"


# Change history
# -------
# 3.16.0:
# Beta-4:
# Add additional comment text
# Clear IOG car charging plan once end time is reached
# Beta-5:
# Supress any negative values after substracting EV consumption from Total Consumption
# Beta-6:
# Tidy up debug logging behind debug switch
# Beta-7: 
# Correct typo in _get_io_car_slots
# Beta-8:
# Add fixes for tariff overrides when Octopus Auto = False (to allow development of EV charge control on Agile)
# Beta-9:
# Introduce category based logging (i.e a filter on debug = true)
# Correct error in Forced Discharging introduced in 3.15.4 
# Beta-10:
# Add extra logging of kWh power consumption, and temporarily add logging of all Zappi sensors on startup 

# 3.17.1:
# Beta-1: #Start car charging for Agile
# Tidyup all logging
# Write basic car charging
# Change all car charging variable names to be tariff inspecific (i.e remove "iog" and "io" from names)
# Beta-2: 
# Fixed timezones/UTC conversions in Car charging plan
# Added additional attributes to car_slots and candidate_car_slots for Dashboard display
# Beta-3:
# Corrected logic for car slots when Zappi not seen as part of house load (no inverter holding is necessary)
# Beta-4
# Trial : commented out supression of MQTT generation of "active" in _expose_configs, to correct 3 switches not being written to
# Beta-5 
# Final fixes for trial above to ensure updates to _active don't retrigger optimiser
# Add Debug category "X" for verbose logging of charge/discharge windows
# Calculate EV windows from slots for dashboard display
# Move calculations of EV charging summaries from _write_output to more appropriate place.

# 3.17.1 Beta changes merged back into 3.17.0-Beta-11. 

# 3.17.0 Beta-12
# Fixed factoring
# Reloaded IOG car plan on every optimiser run
# 3.17.0 Beta-13
# Tidied up logging and added additonal logging category "B". 
# 3.17.0 Beta-14
# Fixes to pickup IOG slots that have already started or are <1/2 hour long

# 3.18.0 Beta-15
# Roll minor version to 18 to reflect latest production release
# Change search string on Intelligent Charge Limit/Target to suit new Octopus Energy Integration
# Minor bugfixes and logging fixes
# 3.19.0 Beta-16
# Roll minor version to 19 to reflect latest production release
# Incorporated Sols Cloud changes made in solis.py
# Added Prevent_Discharge functionality
# Added Zappi multiple charger support
# 3.19.0-Beta-17
# Tidy up logging
# round charge current to nearest integer for Solarman_V2 integration
# 3.19.0-Beta-18
# Bugfix: Removed call to setup_schedule if state change includes the word "forced" - resolves multiple optimiser runs every 10 minutes
# 3.19.0-Beta-19
# Tidy up comments, print out version number on each optimiser run
# 3.19.0-Beta-20
# Incorporate Pull Request #312 changes from main into dev
# 3.19.0-Beta-21
# Reload IOG pricing on every optimiser run from BottlecapDave Octopus Energy Integration
# moved get_io_tariffs from pypy.py to pv_opt.py (to enable the above)
# Changed Solax holding current from 1W to 1A (to prevent Sleep SOC)
# Made self.io_prices a global variable (workaround/hack - needs fixing properly via variable passing between classes)
# Corrected error in "value_changed" logic that meant if the end minutes werent changed, the inverter would not be updated
#  for the Solax_modbus integration

OCTOPUS_PRODUCT_URL = r"https://api.octopus.energy/v1/products/"

DEBUG = False

# Filter Logging when debug = true.
# Valid values for "Debug_categories" are:

# S = Startup/Initialisation Logging
# T = Tariff loading Logging
# P = Power consumption history Logging
# Q = Power consumption debugging (verbose)
# C = Charge algorithm Logging
# D = Discharge algorithm Logging
# W = Charge/Discharge Windows Logging
# X = Charge/Discharge Windows Logging (verbose)
# F = Power Flows Logging
# V = Power Flows debugging (verbose)
# I = inverter control/commands Logging
# E = EV debugging

# Default is all, include desired string in Config.yaml to enable filtering

DEBUG_CATEGORIES = "STPQCDWOXFVIE"

DATE_TIME_FORMAT_LONG = "%Y-%m-%d %H:%M:%S%z"
DATE_TIME_FORMAT_SHORT = "%d-%b %H:%M %Z"
TIME_FORMAT = "%H:%M"

REDACT_REGEX = [
    "[0-9]{2}m[0-9]{7}_[0-9]{13}",  # Serial_MPAN
    "[0-9]{2}e[0-9]{7}_[0-9]{13}",  # Serial_MPAN
    "[a-zA-Z0-9]{10}_[0-9]{13}",  # MeterSerial_MPAN
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
WRITE_POLL_TIME_SLEEP = 2  #added for Solarman_V2 integration that writes to HA entities of type time. 
                           #Using WRITE_POLL_SLEEP value of 0.5 is not sufficient)
WRITE_POLL_RETRIES = 5
GET_STATE_RETRIES = 5
GET_STATE_WAIT = 0.5

BOTTLECAP_DAVE = {
    "domain": "event",
    "domain1": "binary_sensor",
    "domain2": "number",
    "tariff_code": "tariff_code",
    "rates": "current_day_rates",
}

# Create an array of times in the day in 30-minute intervals
BASE_TIME = datetime.strptime("00:00", "%H:%M")
OPTIONS_TIME = [((BASE_TIME + timedelta(seconds=minute * 60)).strftime("%H:%M")) for minute in range(0, 24 * 60, 30)]


INVERTER_TYPES = [
    "SOLIS_SOLAX_MODBUS",
    "SOLIS_CORE_MODBUS",
    "SOLIS_SOLARMAN",
    "SOLIS_SOLARMAN_V2", 
    "SUNSYNK_SOLARSYNK2",
    "SOLAX_X1",
    # "SOLIS_CLOUD",
]

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
    "ev_part_of_house_load": {"default": True, "domain": "switch"},
    "prevent_discharge": {"default": False, "domain": "switch"},
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
            "max": 20.0,
            "step": 0.5,
            "mode": "slider",
        },
        "domain": "number",
    },
    "plunge_threshold_p_kwh": {
        "default": -5.0,
        "attributes": {
            "min": -15.0,
            "max": 10.0,
            "step": 1,
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
            "max": 30000,
            "step": 500,
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
    "battery_current_limit_amps": {
        "default": 100,
        "domain": "number",
        "attributes": {
            "min": 0,
            "max": 300,
            "step": 10,
            "unit_of_measurement": "A",
            "device_class": "current",
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
        "default": 50,
        "domain": "number",
        "attributes": {
            "min": 5,
            "max": 120,
            "step": 1,
            "unit_of_measurement": "kWh",
            "device_class": "energy",
            "mode": "slider",
        },
    },
    "ev_charger": {
        "default": "None",
        "domain": "select",
        "attributes": {
            "options": [
                "None",
                "Zappi",
                "Other",
            ]
        },
        "domain": "select",
    },
    "ev_charger_efficiency_percent": {
        "default": 92,
        "domain": "number",
        "attributes": {
            "min": 80,
            "max": 100,
            "step": 1,
            "unit_of_measurement": "%",
            "mode": "slider",
        },
    },
    "max_ev_price_p": {
        "default": 10.0,
        "attributes": {
            "min": 0.0,
            "max": 40.0,
            "step": 0.5,
            "mode": "slider",
        },
        "domain": "number",
    },
    "ev_charge_target_percent": {
        "default": 80,
        "domain": "number",
        "attributes": {
            "min": 10,
            "max": 100,
            "step": 1,
            "unit_of_measurement": "%",
            "mode": "slider",
        },
    },
    "car_charging_ready_by": {
        "default": "07:00",
        "domain": "select",
        "attributes": {"options": OPTIONS_TIME},
    },
    "control_car_charging": {"default": False, "domain": "switch"},
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
    "consumption_shape": {
        "default": [
            {"hour": 0, "consumption": 300},
            {"hour": 0.5, "consumption": 200},
            {"hour": 6, "consumption": 150},
            {"hour": 8, "consumption": 500},
            {"hour": 15.5, "consumption": 500},
            {"hour": 17, "consumption": 750},
            {"hour": 22, "consumption": 750},
            {"hour": 24, "consumption": 300},
        ]
    },
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
            "step": 50,
            "unit_of_measurement": "W",
            "device_class": "power",
            "mode": "slider",
        },
    },
    "maximum_soc": {
        "default": 100,
        "domain": "number",
        "attributes": {
            "min": 0,
            "max": 100,
            "step": 5,
            "unit_of_measurement": "%",
            "device_class": "battery",
            "mode": "slider",
        },
    },
    "wakeup_soc": {
        "default": 0,
        "domain": "number",
        "attributes": {
            "min": 0,
            "max": 100,
            "step": 5,
            "unit_of_measurement": "%",
            "device_class": "battery",
            "mode": "slider",
        },
    },
    # "alt_tariffs": {"default": [], "domain": "input_select"},
    "charge_active": {"default": True, "domain": "switch"},
    "discharge_active": {"default": True, "domain": "switch"},
    "hold_soc_active": {"default": True, "domain": "switch"},
    "sleep_soc": {
        "default": 0,
        "domain": "number",
        "attributes": {
            "min": 0,
            "max": 20,
            "step": 1,
            "unit_of_measurement": "%",
            "device_class": "battery",
            "mode": "slider",
        },
    },
    "transfer_car_charge_plan": {
        "default": False, "domain": "switch",
    },
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
        self.change_items = {}
        self.config_state = {}
        self.log("")
        self.log(f"*************** PV Opt Version: v{VERSION} ***************")
        self.log("")
        self.io = False
        self.agile = False
        self.ev = False
        self.debug = DEBUG
        self.debug_cat = DEBUG_CATEGORIES
        self.redact_regex = REDACT_REGEX
        self.contract_last_loaded = pd.Timestamp("1970-01-01", tz="UTC")
        try:
            subver = int(VERSION.split(".")[2])
        except:
            self.log("Pre-release version. Enabling debug logging")
            self.debug = True

        self.debug = self.args.get("debug", self.debug)
        self.debug_cat = self.args.get("debug_categories", self.debug_cat)

        self.log(f"Debug Categories selected = {self.debug_cat}")

        if not self.debug:
            self.log("Debug set to false in config.yaml. Disabling debug loggging")

        if self.debug:
            self.log(f"Debug Categories selected = {self.debug_cat}")

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
            self.status(e)
            self.log(e, level="ERROR")
            raise Exception(e)
        else:
            self.log("Inverter appears to be online")

        if (self.debug and "S" in self.debug_cat) or self.args.get("list_entities", True):
            self._list_entities()

        self.timer_handle = None
        self.handles = {}
        self.mqtt_handles = {}

        self.mpans = []

        self.saving_events = {}
        self.contract = None
        self.car_plugin_detected = 0
        self.car_plugin_detected_delayed = 0
        self.tariff_reloaded = 0
        self.agile_car_plan_activated = 0
        self.car_charging_slot = "Off"
        self.candidate_car_slots = pd.DataFrame()
        self.car_slots = pd.DataFrame()
        self.ev_windows = pd.DataFrame()
        self.contract_last_loaded = pd.Timestamp(2024,1,1)
        self.car_slots_last_loaded = pd.Timestamp(2024,1,1)
        self.agile_prices_updated = False
        self.candidate_ev_total_charge = 0
        self.candidate_ev_total_cost = 0
        self.candidate_ev_percent_to_add = 0
        self.ev_total_charge = 0
        self.ev_total_cost = 0
        self.ev_percent_to_add = 0
        self.car_charging = False
        
        self.bottlecap_entities = {"import": None, "export": None}
        self.octopus_import_entity = []

        # Load arguments from the YAML file
        # If there are none then use the defaults in DEFAULT_CONFIG and DEFAULT_CONFIG_BY_BRAND
        # if there are existing entities for the configs in HA then read those values
        # if not, set up entities using MQTT discovery and write the initial state to them
        self._load_args()

        # self._estimate_capacity()
        self._load_pv_system_model()
        self._load_contract()
        self.ev = self.get_config("ev_charger") in DEFAULT_CONFIG["ev_charger"]["attributes"]["options"][1:]  # Is set true only for Zappi at this point
        self.car_charging = self.get_config("control_car_charging")
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

        if self.debug and "S" in self.debug_cat:
            self.log(f"PV Opt Initialisation complete. Listen_state Handles:")
            for id in self.handles:
                self.log(f"  {id} {self.handles[id]}  {self.info_listen_state(self.handles[id])}")

    @ad.app_lock
    def _run_test(self):
        self.ulog("Test")

        test = {
            item: self.get_ha_value(entity_id=self.ha_entities[f"test_{item}"])
            for item in ["start", "end", "power", "enable", "function", "target_soc"]
        }

        for x in ["start", "end"]:
            test[x] = pd.Timestamp(test[x], tz=self.tz)

        test["enable"] = test["enable"].lower() == "enable"
        function = test.pop("function").lower()

        self._log_inverterstatus(self.inverter.status)

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
                self.status(f"Waiting for Modbus Read cycle: {i}")
                time.sleep(1)
                i -= 1

        self._log_inverterstatus(self.inverter.status)

    def _get_io_sensors(self):
        # Get Car charging plan and % charge to add from IO sensors in Bottlecap Dave integration
        self.ulog("Getting Car Charging Plan")
        if self.get_config("octopus_auto"):
            try:
                self.log(f"    Trying to find Octopus Intelligent Dispatching Sensor from Octopus Energy Integration")
                io_dispatching_sensor = [
                    name
                    for name in self.get_state_retry(BOTTLECAP_DAVE["domain1"]).keys()
                    if ("octopus_energy_" in name and "intelligent_dispatching" in name)
                ]
                self.io_dispatching_sensor = io_dispatching_sensor[0]

                self.rlog(f"    Found Dispatching Sensor:  {self.io_dispatching_sensor}")
                self.log("")
                self.log(f"    Trying to find Car % Charge to add from Octopus Energy Integration")
                io_charge_to_add_sensor = [
                    name
                    for name in self.get_state_retry(BOTTLECAP_DAVE["domain2"]).keys()
                    if ("octopus_energy_" in name and "intelligent_charge_" in name)
                ]
                self.io_charge_to_add_sensor = io_charge_to_add_sensor[0]
                self.rlog(f"    Found Charge to Add entity:  {self.io_charge_to_add_sensor}")

                self.io_charge_to_add = self.get_state(
                    self.io_charge_to_add_sensor
                )  # Load the current charge to add value
                self.old_io_charge_to_add = self.io_charge_to_add  # And set historic value to be the same
                self.rlog(f"    Charge to Add Value = :  {self.io_charge_to_add}")

            except Exception as e:
                self.log(f"{e.__traceback__.tb_lineno}: {e}", level="ERROR")
                self.log(
                    "Failed to find Octopus Intelligent Dispatching Sensor and/or % Charge to Add from Octopus Energy Integration. Car charging cannot be determined",
                    level="WARNING",
                )
        else:  # No access to Octopus for loading charge to add
            self.io_charge_to_add = 0  # Set default value of 0
            self.old_io_charge_to_add = 0


    def get_io_tariffs(self, entity_id1):

        x = {}
        y = {}

        # Load tariffs from bottlecapdave .event sensors
        self.log("")
        self.log("    Downloading IOG pricing information from Octopus Energy Integration")

        x = pd.DataFrame(self.get_state_retry(entity_id1, attribute=("rates")))
        # self.log("")
        # self.log("Read of Bottlecap current day rate entity simplfied is.....")
        # self.log(x.to_string())

        if not x.empty:
            x = x.set_index("start")["value_inc_vat"]
            x.index = pd.to_datetime(x.index)
            x.index = x.index.tz_convert("UTC")
            x *= 100
            # SVB logging
            self.rlog(f"      Reading current day IOG prices from  {entity_id1}")

            if (self.debug and "T" in self.debug_cat):
                self.log(f"\n{x.to_string()}")
        else:
            self.log("      No data found in current day rate")

        # current_day_rates loaded, change the entity name to next_day_rates
        entity_id1 = entity_id1.replace("_current_day_rates", "_next_day_rates")

        y = pd.DataFrame(self.get_state_retry(entity_id1, attribute=("rates")))

        if (self.debug and "T" in self.debug_cat):
            self.log("")
            self.log("Read of Bottlecap next day rate entity simplfied is.....")
            self.log(f"\n{y.to_string()}")


        if not y.empty:
            y = y.set_index("start")["value_inc_vat"]
            y.index = pd.to_datetime(y.index)
            y.index = y.index.tz_convert("UTC")
            y *= 100
            self.rlog(f"      Reading next day IOG prices from  {entity_id1}")

            if (self.debug and "T" in self.debug_cat):
                self.log(f"\n{y.to_string()}")

        else:
            self.log("      No data found in next day rate")

        # Concatenate todays and tomorrows tariffs into one DataSeries
        if not x.empty:
            z = x.combine_first(y)
            if (self.debug and "T" in self.debug_cat):
                self.log("")
                self.log("IOG prices are")
                self.log(f"\n{z.to_string()}")
        else:
            z = y

        return z


    def _get_io_car_slots(self):
        # IOG: Get Planned Car dispatches from Intelligent Dispatching sensor
        self.ulog("Reloading IOG Car slots from Intelligent Dispatching Sensor")
        self.io_dispatch_active = self.get_state(self.io_dispatching_sensor)

        self.log(f"  Current Dispatch Status (On/off) = : {self.io_dispatch_active}")

        if self.debug and "E" in self.debug_cat:
            self.io_dispatch_attrib = self.get_state(self.io_dispatching_sensor, attribute="all")
            for k in [x for x in self.io_dispatch_attrib.keys() if "dispatches" not in x]:
                self.rlog(f" {k:20s} {self.io_dispatch_attrib[k]}")

            for k in [x for x in self.io_dispatch_attrib.keys() if "dispatches" in x]:
                self.log(f"  {k:20s} {'Start':20s} {'End':20s} {'Charge':12s} {'Source':12s}")
                self.log(f"  {'-'*20} {'-'*20} {'-'*20} {'-'*12} {'-'*12} ")
                for z in self.io_dispatch_attrib[k]:
                    self.log(
                        f"  {z['start'].strftime(DATE_TIME_FORMAT_LONG):20s}  {z['end'].strftime(DATE_TIME_FORMAT_LONG):20s}  {z['charge_in_kwh']:12.3f}  {z['source']:12s}"
                    )

        # Get Planned dispatches from Intelligent Dispathing sensor
        df = pd.DataFrame(self.get_state_retry(self.io_dispatching_sensor, attribute=("planned_dispatches")))

        # If Charging plan exists, convert dispatch start and end times to datetime format and append to df.
        if not df.empty:
            df["start_dt"] = pd.to_datetime(df["start"])
            df["end_dt"] = pd.to_datetime(df["end"])
            df["start_local"] = df["start_dt"].dt.tz_convert(self.tz)
            df["end_local"] = df["end_dt"].dt.tz_convert(self.tz)

        
        self.log("")
        self.log("    Octopus Intelligent Go Smart Charging Schedule is.... ")

        # self.log(df.to_string())
        # self.log(df.dtypes)
        # self.log(df.info)

        for window in df.iterrows():
            self.log(
                f"    {window[1]['start_dt'].tz_convert(self.tz).strftime('%H:%M'):>7s} to {window[1]['end_dt'].tz_convert(self.tz).strftime('%H:%M'):<7s}  Charge: {window[1]['charge_in_kwh']:7.2f}kWh"
            )

        if len(df) == 0:
            self.log("    No IOG Smart Charging Schedule found.")

        return df

    def _check_car_plugin_iog(self):

        # If a Zappi entity previously found/configured and EV charger is Zappi, schedule an IOG tariff reload on the next optimizer run when its
        # detected the car has been plugged in.
              
        if (len(self.zappi_plug_entity) > 0) and self.ev:
            plug_status = self.get_state(self.zappi_plug_entity)
            # self.log(plug_status)
            if ((plug_status == "EV Connected") or (plug_status == "EV Ready to Charge")) and (
                self.tariff_reloaded == 0
            ):
                self.car_plugin_detected = 1
                self.log("EV plug-in event detected, IOG tariff reload scheduled for next optimiser run")

            elif ((plug_status == "EV Connected") or (plug_status == "EV Ready to Charge")) and (
                self.tariff_reloaded == 1
            ):
                self.log("EV is connected but IOG tariff reload previously caried out. IOG tariff not reloaded")
                self.car_plugin_detected = 0

            elif (plug_status == "Charging") and (self.tariff_reloaded == 0):
                self.log(
                    "EV plug-in event detected and car has commenced charging. IOG tariff reload scheduled for next optimiser run"
                )
                self.car_plugin_detected = 1

            elif (plug_status == "Charging") and (self.tariff_reloaded == 1):
                self.log("EV is charging but IOG tariff reload previously carried out. IOG tariff not reloaded")
                self.car_plugin_detected = 0

            else:
                self.log("EV not plugged in. IOG tariff reload not necessary")
                self.car_plugin_detected = 0

            # If EV plugged in, check charge to add hasnt changed
            if self.get_config("octopus_auto"):
                self.io_charge_to_add = self.get_state(self.io_charge_to_add_sensor)
                if (self.old_io_charge_to_add != self.io_charge_to_add) and (plug_status == "EV Connected"):
                    self.car_plugin_detected = 1
                    self.log("Charge to add changed, IOG tariff reload scheduled for next optimiser run")
            else:
                self.log("Octopus Energy Integration not detected (or disabled): Charge to add is not available, IOG tariff not reloaded")

    def _check_car_plugin_agile(self):

        # If Zappi entity previously found/selected and EV charger is Zappi, trigger a car charging plan to be generated on car plugin
        # If more than one charger, currently limited to 1. 
        # However, there is no reason why the whole of this logic cannot be replicated for multiple chargers.

        if (len(self.zappi_plug_entity) > 0) and self.ev: 
            plug_status = self.get_state(self.zappi_plug_entity)
            # self.log(plug_status)
            if ((plug_status == "EV Connected") or (plug_status == "EV Ready to Charge")) and (self.car_plugin_detected_delayed == 0):
                self.car_plugin_detected = 1
                self.log("EV plug-in event detected, transfer Candidate Agile Car Charging Plan to Active Plan")

            elif ((plug_status == "EV Connected") or (plug_status == "EV Ready to Charge")) and (self.car_plugin_detected_delayed == 1) and (self.agile_car_plan_activated == 1):
                self.log("EV is connected but Candidate Car charging plan previously transfered.")
                self.car_plugin_detected = 0

            elif ((plug_status == "EV Connected") or (plug_status == "EV Ready to Charge")) and (self.agile_car_plan_activated == 0):
                self.car_plugin_detected = 1
                self.log("EV is connected but no Car charging plan exists, transfer Candidate Agile Car Charging Plan to Active Plan")

            elif (plug_status == "Charging") and (self.agile_car_plan_activated == 0):  # needed for Pv_opt restart during car charging, where active plan will then be empty
                self.log("Car has commenced charging but no plan exists. Transfer Candidate Plan to Active Plan")
                self.car_plugin_detected = 1

            elif (plug_status == "Charging") and (self.agile_car_plan_activated == 1):
                self.log("EV is charging, Car charging plan already transferred")
                self.car_plugin_detected = 0

            else:
                self.log("EV not plugged in. Car charging plan not required.")
                self.car_plugin_detected = 0
                
            if ((plug_status == "EV Connected") or (plug_status == "EV Ready to Charge")):
                self.car_plugged_in = True
            else:
                self.car_plugged_in = False

    def _check_for_zappi(self):
        self.ulog("Reading Zappi(s)")
        self.log("Attempting to autodetect Zappi consumption sensor(s)")
        sensor_entities = self.get_state("sensor")

        self.zappi_consumption_entities = [k for k in sensor_entities if "zappi" in k for x in ["charge_added_session"] if x in k]

        #force two Zappis for test purposes
        #self.zappi_consumption_entities = ["sensor.myenergi_zappi_12345679_charge_added_session", "sensor.myenergi_zappi_12345678_charge_added_session" ]

        if len(self.zappi_consumption_entities) > 0:
            for entity_id in self.zappi_consumption_entities:
                zappi_sn = entity_id.split("_")[2]
                self.redact_regex.append(zappi_sn)
                self.log("Zappi consumption sensor(s) found:")
                self.rlog(f"  {entity_id}")
                self.log("")
        else:
            self.log("No Zappi Consumption sensors autodetected")


        self.log("Attempting to autodetect Zappi Plugin status sensor(s)")
        self.zappi_plug_entities = [k for k in sensor_entities if "zappi" in k for x in ["plug_status"] if x in k]

        if len(self.zappi_plug_entities) > 0:
            for entity_id in self.zappi_plug_entities:
                zappi_sn = entity_id.split("_")[2]
                self.redact_regex.append(zappi_sn)
                self.log("Zappi plug_status sensor(s) found:")
                self.rlog(f"  {entity_id}")

            self.zappi_plug_entity = self.zappi_plug_entities[0] # If multiple, select the first by default. 
            if len(self.zappi_plug_entities) > 1:
                self.log("")
                self.log(f"Multiple Zappis found, defaulting to {self.zappi_plug_entity} to trigger car charge planning updates." )
                self.log("If necessary, map desired sensor using id_zappi_plug_status in config.yaml")
                self.log("Checking config.yaml for presence of id_zappi_plug_status...")
        else:
            self.log("No Zappi Plug Status sensors autodetected")
            self.log("Checking config.yaml for presence of id_zappi_plug_status....")

        # Check config.yaml for entry of id_zappi_plug_status, if so, override whats autodetected as first entry. 
        
        if "id_zappi_plug_status" in self.config:
            entity_id = self.config["id_zappi_plug_status"]
            self.log("")
            self.log(f"id_zappi_plug_status value in config.yaml = {entity_id}")
            self.log(f"Overriding auto detected plug_status sensor ({self.zappi_plug_entity}) to mapping provided in config.yaml ({entity_id})")
            self.zappi_plug_entity = entity_id
        else:
            self.log("")
            self.log(f"No entry found in config.yaml for plug_status sensor, leaving any autodetected sensor in place.")
        
        self.log("")

    def _get_zappi(self, start, end, log=False):
        df = pd.DataFrame()

        i = 0
        for entity_id in self.zappi_consumption_entities:
            i += 1
            df = self._get_hass_power_from_daily_kwh(entity_id, start=start, end=end, log=log)
            
            if i == 1:
                df_all = df.copy()
            if i > 1: #If more than one charger, add data as extra column
                df_all = pd.concat([df_all, df], axis=1)

            if log and (self.debug and "E" in self.debug_cat):
                self.rlog(f">>> Zappi entity {entity_id}")
                self.log(f">>>\n{df.to_string()}")
                self.log(f">>> Value of i = {i}")
                self.rlog(">>> df_all")
                self.log(f">>>\n{df_all.to_string()}")

              
        df_all = df_all.fillna(0)  # fill any missing values with 0
        if i == 1:
            df = df_all
        if i > 1:
            df = df_all.sum(axis=1)      # sum across columns

        if log and (self.debug and "E" in self.debug_cat):
            self.rlog("Final result of get_zappi......")
            self.log(f">>>\n{df.to_string()}")

        return df
    
    def calculate_agile_car_slots(self):

        # Reload charge target, ready by time and max price on each run
        self.ev_charge_target = self.get_config("ev_charge_target_percent")
        self.ev_ready_by_time = self.get_config("car_charging_ready_by")
        self.ev_max_slot_price = self.get_config("max_ev_price_p")

        if self.debug and "E" in self.debug_cat:
            self.log(f"EV Capacity = {self.ev_capacity}")
            self.log(f"EV Charger Power = {self.ev_charger_power}")
            self.log(f"Charger Efficiency = {self.ev_charger_efficiency}")
            self.log(f"EV slot Max Price = {self.ev_max_slot_price}")
            self.log(f"EV Charge Target = {self.ev_charge_target}")
            self.log(f"EV Ready by time = {self.ev_ready_by_time}")

        # Calculate charge to add in kwh (EV capacity * (SOC target - SOC current) * 1/efficiency)
        charge_kwh = self.ev_capacity * (self.ev_charge_target) * (1 / self.ev_charger_efficiency)

        # self.log("")
        # self.log(f"Charge to add (kwh) = {charge_kwh}")

        # Work out time needed to charge
        ev_charge_time = charge_kwh / (self.ev_charger_power / 1000)
        # self.log(f"Charge time (hours) = {ev_charge_time}")

        ### Code will quantise to full slots only - i.e no partial charging in a half hour slot (which is what IOG does)
        # LAter versions of code will add this

        # Convert to number of slots by mutiplying by 2, then rounding up
        ev_slots_required = math.ceil(ev_charge_time*2)

        self.log(f"EV Charging Candidate plan requires {ev_slots_required} x 1/2 hour slots")
        self.log("")

        # now = datetime.now()
        # ready_by_time = datetime.strptime(self.ev_ready_by_time, "%H:%M")
        
        # Get timenow, this is in local time)
        now = pd.Timestamp.now()
        # self.log(f"Time Now = {now}")

        # Get ready by time, this will also be in local time. 
        ready_by_time = pd.to_datetime(self.ev_ready_by_time, errors="coerce", format="%H:%M")
                
        Y = int(now.strftime("%Y"))    #Extract year
        M = int(now.strftime("%-m"))   #Extract month
        D = int(now.strftime("%-d"))   #Extract day

        ready_by_datetime = ready_by_time.replace(year=Y, month=M, day = D)

        # Is ready time in the past? If so make it the same time tomorrow. 
        if ready_by_datetime < now:
            ready_by_datetime += pd.Timedelta(hours=24)

        # Localise, then convert to UTC
        ready_by_datetime = ready_by_datetime.tz_localize(self.tz)
        ready_by_datetime = ready_by_datetime.tz_convert("UTC")

        df = self.opt [["import", "export"]]
        df["start"] = df.index
        df["end"] = df.index + pd.Timedelta(30, "minutes")


        if self.debug and "E" in self.debug_cat:
            self.log(f"Ready By time after converstion to UTC is = {ready_by_datetime}")
            self.log("Df = ")
            self.log(f"\n{df.to_string()}")
          
        # Trim self.car_charge_slots to remove all slots after "ready_by_datetime"
        df = df[df["start"]  < ready_by_datetime]

        if self.debug and "E" in self.debug_cat:
            self.log(f"\n{df.to_string()}")

        # Reorder dataframe slots to cheapest import slot first
        df = df.sort_values("import")
      
        # Keep the number of rows required to charge the car, delete the rest
        df = df.iloc[:ev_slots_required]

        if self.debug and "E" in self.debug_cat:
            self.log("Slots required for charge")
            self.log(f"\n{df.to_string()}")

        df["start_dt"] = pd.to_datetime(df["start"])
        df["end_dt"] = pd.to_datetime(df["end"])
        df["start_local"] = df["start_dt"].dt.tz_convert(self.tz)
        df["end_local"] = df["end_dt"].dt.tz_convert(self.tz)

        # If max slot price is set to zero then its disabled. 
        # If non-zero, delete all slots that cost above the max price set

        if self.ev_max_slot_price != 0:
            car_charge_slots = df[df["import"] <= self.ev_max_slot_price]
        else:
            car_charge_slots = df

        # Add "charge_in_kwh" col, fixed at charger power * efficiency
        car_charge_slots['charge_in_kwh'] = (self.ev_charger_power / 1000) * (self.ev_charger_efficiency/100 * 0.5)

        # Reorder dataframe back to date order
        car_charge_slots = car_charge_slots.sort_index()

        ev_total_charge = 0
        ev_total_cost = 0
        ev_percent_to_add = 0

        if not car_charge_slots.empty:
            ev_total_charge = car_charge_slots["charge_in_kwh"].sum()
            ev_total_cost = car_charge_slots["import"].sum()
            ev_percent_to_add = (ev_total_charge / self.ev_capacity) * 100

        self.log(f"Target % to add = {self.ev_charge_target:3.0f}%")
        self.log("")

        self.log("Candidate EV Charge Plan:")

        #self.log(f"\n{car_charge_slots.to_string()}")
        #self.log("")

        for window in car_charge_slots.iterrows():
            self.log(
                f"  {window[1]['start_local'].strftime('%d-%b %H:%M %Z'):>13s} - {window[1]['end_local'].strftime('%d-%b %H:%M %Z'):<13s}  Charge: {window[1]['charge_in_kwh']:3.2f}kWh  Slot Price: {window[1]['import']:3.1f}p"
            )
        self.log("")
        self.log(f"Charge to Add = {ev_total_charge} kWh, Total Cost = {ev_total_cost:4.0f}p, % to Add = {ev_percent_to_add:3.0f}%")

        return car_charge_slots, ev_total_charge, ev_total_cost, ev_percent_to_add

    def _control_EV_charger(self): 

        self.log("")
        self.ulog("Updating EV charge control")


        if self.debug and "E" in self.debug_cat:
            self.log("")
            self.log("self.opt is........")
            self.log(f"\n{self.opt.to_string()}")

        if self.opt["carslot"].iloc[0] == 1:
            self.car_charging_slot = "on"
        else:
            self.car_charging_slot = "off"


        ### SVB add a safeguard to ensure charger is off once plan is expired? 
        

        self.log(f"Updating Car_Charging Slot Control to {self.car_charging_slot}")

        self.write_to_hass(
            entity=f"binary_sensor.{self.prefix}_car_charging_slot",
            state=self.car_charging_slot,
            attributes={
                "friendly_name": "Car Charging Slot",
            },
        )
    

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
            self.rlog(f"  Serial number: {self.inverter_sn}")

        else:
            e = f"Inverter type {self.inverter_type} is not yet supported. Only read-only mode with explicit config from the YAML will work."
            self.log(e, level="ERROR")

    def _load_pv_system_model(self):
        self.status("Initialising PV Model")

        self.inverter_model = pv.InverterModel(
            inverter_efficiency=self.get_config("inverter_efficiency_percent") / 100,
            inverter_power=self.get_config("inverter_power_watts"),
            inverter_loss=self.get_config("inverter_loss_watts"),
            charger_efficiency=self.get_config("charger_efficiency_percent") / 100,
            charger_power=self.get_config("charger_power_watts"),
        )

        self.battery_model = pv.BatteryModel(
            capacity=self.get_config("battery_capacity_wh"),
            max_dod=self.get_config("maximum_dod_percent", 15) / 100,
            current_limit_amps=self.get_config("battery_current_limit_amps", default=100),
            voltage=self.get_config("battery_voltage", default=50),
        )
        self.pv_system = pv.PVsystemModel("PV_Opt", self.inverter_model, self.battery_model, host=self)


        ### SVB: once code is up and running for Agile EV charging, should probably put these parameters in something like pv.EvModel (as they don't change)
        # Needs a gate for systems with no EV? Something like:
        # If EV_charger = Zappi then:
        self.ev_capacity = self.get_config("ev_battery_capacity_kwh")
        self.ev_charger_power = self.get_config("ev_charger_power_watts")
        self.ev_charger_efficiency = self.get_config("ev_charger_efficiency_percent")
        self.ev_max_slot_price = self.get_config("max_ev_price_p")
        self.ev_charge_target = self.get_config("ev_charge_target_percent")
        self.ev_ready_by_time = self.get_config("car_charging_ready_by")
            
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

        if self.debug and "F" in self.debug_cat:
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
                x = self.get_ha_value(entity_id=self.config[item])
                return x
            elif isinstance(self.config[item], list):
                if min([isinstance(x, str)] for x in self.config[item])[0]:
                    if min([self.entity_exists(entity_id=entity_id) for entity_id in self.config[item]]):
                        l = [self.get_ha_value(entity_id=entity_id) for entity_id in self.config[item]]
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
        self.status("Loading Tariffs")
        self.rlog("-----------------")
        self.tariff_codes = {}
        self.io_prices = {}
        self.agile = False
        self.intelligent = False

        i = 0
        n = 5

        old_contract = self.contract
        self.contract = None

        while self.contract is None and i < n:
            if self.get_config("octopus_auto"):
                try:
                    self.rlog(f"    Trying to auto detect Octopus tariffs:")

                    octopus_entities = [
                        name
                        for name in self.get_state_retry(BOTTLECAP_DAVE["domain"]).keys()
                        if ("octopus_energy_electricity" in name and BOTTLECAP_DAVE["rates"] in name)
                    ]
                    # self.log("Octopus Entities = ")
                    # self.log(octopus_entities)

                    entities = {}
                    entities["import"] = [x for x in octopus_entities if not "export" in x]
                    entities["export"] = [x for x in octopus_entities if "export" in x]

                    for imp_exp in IMPEXP:
                        for entity in entities[imp_exp]:
                            tariff_code = self.get_state_retry(entity, attribute="all")["attributes"].get(
                                BOTTLECAP_DAVE["tariff_code"], None
                            )

                            self.rlog(f"    Found {imp_exp} entity {entity}: Tariff code: {tariff_code}")

                    tariffs = {x: None for x in IMPEXP}
                    for imp_exp in IMPEXP:
                        if self.debug and "T" in self.debug_cat:
                            self.log(f"    >>>{imp_exp}: {entities[imp_exp]}")

                        if len(entities[imp_exp]) > 0:
                            for entity in entities[imp_exp]:
                                tariff_code = self.get_state_retry(entity, attribute="all")["attributes"].get(
                                    BOTTLECAP_DAVE["tariff_code"], None
                                )

                                if self.debug and "T" in self.debug_cat:
                                    self.log(f">>>X _load_contract {tariff_code}")

                                if tariff_code is not None:
                                    tariffs[imp_exp] = pv.Tariff(
                                        tariff_code,
                                        export=(imp_exp == "export"),
                                        host=self,
                                    )

                                    self.bottlecap_entities[imp_exp] = entity
                                    if "AGILE" in tariff_code:
                                        self.agile = True  # Tariff is Octopus Agile
                                    if "INTELLI" in tariff_code:
                                        self.intelligent = True  # Tariff is Octopus Intelligent
                    # self.log("")
                    # self.log("Printing bottlecap entity list")
                    # self.log(self.bottlecap_entities)

                    self.contract = pv.Contract(
                        "current",
                        imp=tariffs["import"],
                        exp=tariffs["export"],
                        host=self,
                    )

                    if self.intelligent:
                        self._get_io_sensors()  # Find the Octopus Zappi sensors
                        car_slots = self._get_io_car_slots()  # Load the car charging slots

                        #Set import import price to 0 for slots (isnt used/displayed if using IOG, but is in Agile)
                        
                        car_slots['import'] = 0  

                        if self.debug and "E" in self.debug_cat:
                            self.log("")
                            self.log("Car_slots = ")
                            self.log(car_slots.to_string())

                        self.car_slots = car_slots
                        self.car_slots_last_loaded = pd.Timestamp.now(tz="UTC")
                        

                    self.log("")
                    self.log("Contract tariffs loaded OK")

                except Exception as e:
                    self.rlog(f"{e.__traceback__.tb_lineno}: {e}", level="ERROR")
                    self.rlog(
                        "Failed to find tariff from Octopus Energy Integration",
                        level="WARNING",
                    )
                    self.contract = None

            if self.contract is None:  # Try loading using Octopus Account number and API ket
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
                tariffs = {x: None for x in IMPEXP}

                if (
                    "octopus_import_tariff_code" in self.config
                    and self.config["octopus_import_tariff_code"] is not None
                ):
                    self.rlog(f"Trying to load tariff codes: Import: {self.config['octopus_import_tariff_code']}")
                    # try:
                    # First load the import as we always need that
                    tariffs["import"] = pv.Tariff(
                        self.config[f"octopus_import_tariff_code"],
                        export=False,
                        host=self,
                    )
                elif self.get_config("manual_import_tariff", False):
                    tariffs["import"] = self._manual_tariff("import")

                if tariffs["import"] is not None:
                    if "octopus_export_tariff_code" in self.config:
                        self.rlog(f"Trying to load tariff codes: Export: {self.config['octopus_export_tariff_code']}")
                        tariffs["export"] = pv.Tariff(
                            self.config[f"octopus_export_tariff_code"],
                            export=False,
                            host=self,
                        )
                    elif self.get_config("manual_export_tariff", False):
                        tariffs["export"] = self._manual_tariff("export")

                    self.contract = pv.Contract(
                        "current",
                        imp=tariffs["import"],
                        exp=tariffs["export"],
                        host=self,
                    )
                    self.rlog("Contract tariffs loaded OK from Tariff Codes / Manual Spec")
                # except Exception as e:
                #     self.rlog(f"Unable to load Tariff Codes {e}", level="ERROR")

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
            self.contract_last_loaded = pd.Timestamp.now(tz="UTC")

            
            # self.log("Printing self.contract.tariffs at end of 'load_contract'")
            # self.log(self.contract.tariffs)
            # self.log("")

            if self.contract.tariffs["export"] is None:
                self.contract.tariffs["export"] = pv.Tariff("None", export=True, unit=0, octopus=False, host=self)
            self.rlog("")
            self._load_saving_events()

        self.log("")
        self.log("Finished loading contract")

    def _manual_tariff(self, direction="import"):
        name = self.get_config(f"manual_{direction}_tariff_name")
        self.log(f"Trying to load manual {direction} tariff {name}")
        tz = self.get_config(f"manual_{direction}_tariff_tz")
        if direction == "import":
            fixed = self.get_config(f"manual_{direction}_tariff_standing", 0.0)
        else:
            fixed = None
        unit = self.get_config(f"manual_{direction}_tariff_unit")

        return pv.Tariff(
            name=name,
            octopus=False,
            export=(direction == "export"),
            fixed=fixed,
            unit=unit,
            host=self,
            manual=True,
        )

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
                if "INTELLI" in tariff.name:
                    self.intelligent = True

        if self.agile:
            self.log("  AGILE tariff detected. Rates will update at 16:00 daily")

        if self.intelligent:
            self.log(
                "  Octopus Intelligent Go tariff detected. Rates will be downloaded at midnight, 04:40 and 16:40, and on car plugin"
            )

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
            self.log("  The following Octopus Saving Events have been joined:")
            for id in self.saving_events:
                self.log(
                    f"{id:8d}: {pd.Timestamp(self.saving_events[id]['start']).strftime(DATE_TIME_FORMAT_SHORT)} - {pd.Timestamp(self.saving_events[id]['end']).strftime(DATE_TIME_FORMAT_SHORT)} at {int(self.saving_events[id]['octopoints_per_kwh'])/8:5.1f}p/kWh"
                )
        else:
            self.log("  No upcoming Octopus Saving Events detected or joined:")

    def get_ha_value(self, entity_id):
        value = None

        # if the entity doesn't exist return None
        if self.entity_exists(entity_id=entity_id):
            state = self.get_state_retry(entity_id=entity_id)

            # if the state is None return None
            if state is not None:
                if (state in ["unknown", "unavailable"]) and (entity_id[:6] != "button"):
                    e = f"HA returned {state} for state of {entity_id}"
                    self.status(f"ERROR: {e}")
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
        if self.debug and "S" in self.debug_cat:
            self.rlog(self.args)

        self.prefix = self.args.get("prefix", "solis")

        self.status("Loading Configuation")
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

            elif item == "consumption_shape":
                self.config[item] = values
                for i, x in enumerate(values):
                    if i == 0:
                        str1 = item
                        str2 = "="
                        str3 = "Hour:"
                        str4 = "Consumption:"
                    else:
                        str1 = ""
                        str2 = " "
                        str3 = "     "
                        str4 = "            "
                    self.rlog(f"    {str1:34s} {str2} {str3} {x['hour']:5.2f} {str4} {x['consumption']:5.0f} W")
                self.yaml_config[item] = self.config[item]

            elif re.match("^manual_..port_tariff_unit$", item):
                self.config[item] = values
                for i, x in enumerate(values):
                    if i == 0:
                        str1 = item
                        str2 = "="
                        str3 = "Period Start:"
                        str4 = "Price:"
                    else:
                        str1 = ""
                        str2 = " "
                        str3 = "             "
                        str4 = "      "
                    self.rlog(
                        f"    {str1:34s} {str2} {str3} {pd.Timestamp(x['period_start']).strftime('%H:%M')} {str4} {x['price']:5.0f} p/kWh"
                    )
                self.yaml_config[item] = self.config[item]

            elif "id_" in item:
                if self.debug:
                    self.log(f">>> Test: {self.entity_exists('update.home_assistant_core_update')}")
                    for v in values:
                        self.log(f">>> {item} {v} {self.entity_exists(v)}")
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
                if self.debug and "S" in self.debug_cat:
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
                    if self.debug and "S" in self.debug_cat:
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
                            if not "sensor" and not "_active" in valid_strings[0][1]:   #SVB trial
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
                    if self.debug and "S" in self.debug_cat:
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
                    if self.debug and "S" in self.debug_cat:
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
                            if not "sensor" and not "_active" in v:   #SVB trial
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
                isinstance(self.get_ha_value(entity_id=entity_id), str)
                and (self.get_ha_value(entity_id=entity_id) not in attributes.get("options", {}))
                and (domain not in ["text", "button"])
            ) or (self.get_ha_value(entity_id=entity_id) is None):

                state = self._state_from_value(self.get_default_config(item))

                self.log(f"  - Found unexpected str for {entity_id} reverting to default of {state}")

                self.set_state(state=state, entity_id=entity_id)

            elif item in self.yaml_config:
                state = self.get_state_retry(entity_id)
                new_state = str(self._state_from_value(self.config[item]))
                if (over_write and state != new_state) or (state is None):
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
                if not not "sensor" and not "_active" in entity_id:
                    item = self.change_items[entity_id]
                    self.log(f"  {item:40s}  {entity_id:42s}  {self.config_state[item]}")
                    self.handles[entity_id] = self.listen_state(
                        callback=self.optimise_state_change, entity_id=entity_id
                    )
                    self.ha_entities[item] = entity_id

        self.mqtt.listen_state(
            callback=self.optimise_state_change,
        )

    def status(self, status):
        entity_id = f"sensor.{self.prefix.lower()}_status"
        attributes = {"last_updated": pd.Timestamp.now().strftime(DATE_TIME_FORMAT_LONG)}
        # self.log(f">>> {status}")
        # self.log(f">>> {entity_id}")
        self.set_state(state=status, entity_id=entity_id, attributes=attributes)

    @ad.app_lock
    def optimise_state_change(self, entity_id, attribute, old, new, kwargs):
        item = self.change_items[entity_id]
        self.log(f"State change detected for {entity_id} [config item: {item}] from {old} to {new}:")

        self.config_state[item] = new

        # SVB 25/11/2024
        # Commented out call to setup_schedule - it shouldn't be needed to do something special if the Optimised Discharge (forced_discharge) entity is toggled. Having
        # it appears to generate an addtional optimiser callback every 10 minutes that then persists forever, so removed. 
        # Believed to be a hangover from when the charging and discharging algorithms had thier own seperate callbacks, long since removed. 

        #if "forced" in item:
        #    self._setup_schedule()


        ### SVB: Add additional EV items to this list: Car capacity, charger efficiency, charger power, and add an Ev model to pv_system_model routine
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
        self.log(f"Version: v{VERSION}")
        self.optimise()

    @ad.app_lock
    def optimise(self):
        # initialse a DataFrame to cover today and tomorrow at 30 minute frequency

        self.log("")
        self._load_saving_events()

        if self.get_config("forced_discharge") and (self.get_config("supports_forced_discharge", True)):
            discharge_enable = "enabled"
        else:
            discharge_enable = "disabled"

        self.log("")
        self.log(f"Starting Opimisation with discharge {discharge_enable}")
        self.log(f"------------------------------------{len(discharge_enable)*'-'}")

        self.ulog("Checking tariffs:")

        self.log(f"  Contract last loaded at {self.contract_last_loaded.strftime(DATE_TIME_FORMAT_SHORT)}")

        # Reload Ev selector status
        self.ev = self.get_config("ev_charger") in DEFAULT_CONFIG["ev_charger"]["attributes"]["options"][1:]  # Is set true only for Zappi at this point

        # Reload EV Charge plan control
        self.car_charging = self.get_config("control_car_charging")

        if self.agile:
            if (self.contract.tariffs["import"].end().day == pd.Timestamp.now().day) and (
                pd.Timestamp.now(tz=self.tz).hour >= 16
            ):
                self.log(
                    f"Contract end day: {self.contract.tariffs['import'].end().day} Today:{pd.Timestamp.now().day}"
                )
                self._load_contract()
                self.agile_prices_updated = True

        elif self.intelligent:
            # self.log("Printing time.....")
            # self.log(pd.Timestamp.now(tz=self.tz).hour)
            if (pd.Timestamp.now(tz=self.tz).hour == 16) and (pd.Timestamp.now(tz=self.tz).minute >= 40):
                self.log("   About to reload Octopus Intelligent Pricing - 16:40")
                self._load_contract()
                
            if (pd.Timestamp.now(tz=self.tz).hour == 0) and (pd.Timestamp.now(tz=self.tz).minute <= 20):
                self.log("   About to reload Octopus Intelligent Pricing - 00:20")
                self._load_contract()
                
            if (pd.Timestamp.now(tz=self.tz).hour == 5) and (pd.Timestamp.now(tz=self.tz).minute >= 10):
                self.log("   About to reload Octopus Intelligent Pricing - 05:10")
                self._load_contract()
                
            if self.car_plugin_detected == 1:
                self.log(
                    "Car plugin detected or charge to add value changed. About to reload Octopus Intelligent Pricing"
                )
                self._load_contract()
                self.tariff_reloaded = 1

            # reload pricing from bottlecap dave sensors on every optimiser run
            
            self.log("")
            self.ulog("Reload IOG prices from Octopus Energy Integration")

            self.io_prices = self.get_io_tariffs(self.octopus_import_entity[0])
            

        elif self.contract_last_loaded.day != pd.Timestamp.now(tz="UTC").day:
            self._load_contract()

        if self._check_tariffs():
            self.log("")
            self.log("  Tariff error detected. Attempting to re-load.")
            self.log("")
            self._load_contract()
        else:
            self.log("  Tariffs OK")
            self.log("")

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

        self.soc_now = self.get_config("id_battery_soc")
        x = self.hass2df(self.config["id_battery_soc"], days=1, log=self.debug)
        if self.debug and "S" in self.debug_cat:
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
        if self.debug and "S" in self.debug_cat:
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
            self.status("ERROR: No initial SOC")
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
            self.status("ERROR: Baseline performance")
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

        self.status("Optimising charge plan")

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
        cost_today = self._cost_actual().sum()
        self.summary_costs = {
            "Base": {"cost": ((self.optimised_cost["Base"].sum() + cost_today) / 100).round(2), "Selected": ""}
        }
        for case in cases:
            str_log = f"  {f'Optimised cost ({case}):':40s} {self.optimised_cost[case].sum():6.1f}p"
            self.summary_costs[case] = {"cost": ((self.optimised_cost[case].sum() + cost_today) / 100).round(2)}
            if case == self.selected_case:
                self.summary_costs[case]["Selected"] = " <=== Current Setup"
            else:
                self.summary_costs[case]["Selected"] = ""

            self.log(str_log + self.summary_costs[case]["Selected"])

        self.opt = self.flows[self.selected_case]

        # SVB debug logging
        #self.log("")
        #self.log("Returned from .flows. self.opt is........")
        #self.log(f"\n{self.opt.to_string()}")

        # create a df with an index value the same as self.opt (just copy it from self.opt)
        # Copy two columns to force y to be a dataframe

        y = self.opt.loc[:, ["import", "forced"]].copy()

        y["start"] = self.opt.index.tz_convert(self.tz).copy()
        y["end"] = self.opt.index.tz_convert(self.tz).copy() + pd.Timedelta(30, "minutes")

        #self.log("")
        #self.log("Y is........")
        #self.log(f"\n{y.to_string()}")
       

        # Create a Pd series to store any 1/2 hour car charge slots  (1 = car charge slot, 0 = not a car charge slot)
        # Note: self.opt will now include attribute "carslot" regardless of actual tariff, but be set 
        # to 0 unless on 1) IOG and dispatches are planned or 2) Car charging on agile is required
        car_on = pd.Series(index=y.index, data=0, name="carslot")

        # If on IOG tariff, "self.car_slots" will have already been calculated via a Contract load on car plugin
        # However, with recent changes (Nov 2024) to the IOG algorithms they are now changing the slots regularly, so load them every optimiser run.

        if self.intelligent:
            car_slots = self._get_io_car_slots()  # Load the car charging slots
            car_slots['import'] = 0
            self.car_slots = car_slots
            self.car_slots_last_loaded = pd.Timestamp.now(tz="UTC")
        
        # If on Agile tariff, (re)calculate car slots now. 

        if self.agile and self.ev and self.car_charging:
            self.log("")
            self.ulog("Calculating candidate Car Charging Plan")
            self.candidate_car_slots, self.candidate_ev_total_charge, self.candidate_ev_total_cost, self.candidate_ev_percent_to_add = self.calculate_agile_car_slots()

        if self.debug and "E" in self.debug_cat:
            self.log("Self.candidate_car_slots is")
            self.log(self.candidate_car_slots.to_string())

            self.log("self.car_slots is")
            self.log(self.car_slots.to_string())

            self.log("y is")
            self.log(y.to_string())

        # For each time range in the IOG Charging Schedule/Agile Car Charge Plan, set 1/2 hour Car slot flag to "1"
        # Problem: If the car is plugged in and starts to charge, car slot flag is not being set. 
        # i.e y(start) = 22:00, car_slots(start) = 22:07 should set a car_on flag but it isnt. 
        # need to not only use y["start"] but also y["end"] to search. 
        if not self.car_slots.empty and self.ev:
            for h in range(len(self.car_slots)):
                for i in range(len(y)):
                    #self.log(f"i is {i}")
                    if (y["start"].iloc[i] >= self.car_slots["start_dt"].iloc[h]) and (
                        y["start"].iloc[i] < self.car_slots["end_dt"].iloc[h]
                    ):
                    # Repeat for end times in case car just plugged in and already charging
                    # also needed for IOG slots that are less than 1/2 hour long. 
                        car_on.iat[i] = 1
                    if (y["end"].iloc[i] > self.car_slots["start_dt"].iloc[h]) and (
                        y["end"].iloc[i] <= self.car_slots["end_dt"].iloc[h]
                    ):
                        car_on.iat[i] = 1

        # Read "prevent_discharge" switch to set a car slot in the current slot and next slot

        if self.get_config("prevent_discharge"):
            car_on.iat[0] = 1
            car_on.iat[1] = 1

        self.opt = pd.concat([self.opt, car_on], axis=1)  # Add car charge slot flags to self.opt

        # Clear off any expired car slots so dashboard displays correctly
        if not self.car_slots.empty:
            self.car_slots = self.car_slots.drop(
                self.car_slots[self.car_slots["end_dt"] < pd.Timestamp.now(self.tz)].index
            )

            if self.debug and "E" in self.debug_cat:
                self.log("Car slot clearance check")
                self.log(self.car_slots["end_dt"])
                self.log(pd.Timestamp.now(self.tz))

        # If no Charger selected, clear self.car_slots (catchall / helps with testing)
        if not self.ev:
            self.car_slots = pd.DataFrame()

        # If Agile Tariff and car charging turned off, clear self.car_slots (catchall / helps with testing)
        if self.agile and not self.car_charging:
            self.car_slots = pd.DataFrame()

            
        if self.intelligent and self.ev:
            self.log("")
            self.ulog("Checking EV Status (IOG tariff)")
            self._check_car_plugin_iog()

        if self.agile and self.ev and self.car_charging:
            self.log("")
            self.ulog("Checking EV Status (Agile Tariff)")
            self._check_car_plugin_agile()
            
            # Copy candidate car slots to active plan upon 
            # 1) plugin detected
            # 2) new agile prices are available (and EV is plugged in)
            # 3) Transfer button is pressed

            #For 3: Check if Manual transfer button is pressed
            car_button = self.get_config("transfer_car_charge_plan")

            if self.debug and "E" in self.debug_cat:
                self.log(f"Car_plugin_detected = {self.car_plugin_detected}")
                self.log(f"Agile_prices_updated = {self.agile_prices_updated}")
                self.log(f"Transfer_car_charge_plan = {car_button}")

            ### Currently there is nothing that clears "self.agile_prices_updated". I think this only needs doing if the car is already plugged in,
              # so just clear it after this routine is finished? (i.e. not within the if)

            if (self.car_plugin_detected == 1 and self.car_plugin_detected_delayed == 0) or (self.agile_prices_updated and self.car_plugged_in) or car_button == True: 
                self.log("Transferring EV Candidate Plan to Active Plan")

                
                if self.debug and "E" in self.debug_cat:
                    self.log("Candidate Plan is:.....")
                    self.log(f"\n{self.candidate_car_slots.to_string()}")
    
                    self.log("Active Plan before transfer is.....")
                    self.log(f"\n{self.car_slots.to_string()}")
                    self.log("Active Plan last loaded (UTC).....")
                    self.log(self.car_slots_last_loaded)
                
                self.car_slots = self.candidate_car_slots

                if self.debug and "E" in self.debug_cat:
                    self.log("Active Plan after transfer is:.....")
                    self.log(f"\n{self.car_slots.to_string()}")
                
                self.agile_car_plan_activated = 1            #Set car plan active flag
                self.car_plugin_detected_delayed = self.car_plugin_detected         
                
                # Set the manual transfer switch back to off (if routine triggered by manual car switch)
                if car_button:
                    self.write_to_hass(state="off", entity=f"switch.{self.prefix}_transfer_car_charge_plan")
                # Update plan time transfer for display in Dashboard
                self.car_slots_last_loaded = pd.Timestamp.now(tz="UTC")

            #Calculate summary for active plan, for dashboard display
        
            if not self.car_slots.empty:
                self.ev_total_charge = self.car_slots["charge_in_kwh"].sum()
                self.ev_total_cost = self.car_slots["import"].sum()
                self.ev_percent_to_add = (self.ev_total_charge / self.ev_capacity) * 100

                self.log("")
                self.log("Active EV charge plan:")

                #self.log(f"\n{self.car_slots.to_string()}")
                #self.log("")

                for window in self.car_slots.iterrows():
                    self.log(
                        f"  {window[1]['start_local'].strftime('%d-%b %H:%M %Z'):>13s} - {window[1]['end_local'].strftime('%d-%b %H:%M %Z'):<13s}  Charge: {window[1]['charge_in_kwh']:3.2f}kWh  Slot Price: {window[1]['import']:3.1f}p"
                    )
                self.log("")
                self.log(f"Charge to Add = {self.ev_total_charge} kWh, Total Cost = {self.ev_total_cost:4.0f}p, % to Add = {self.ev_percent_to_add:3.0f}%")
            else:
                self.log("")
                self.log("No Active EV Charge Plan")
                self.log("")


        # If all slots expired then car charging plan is finished, clear activation flags.
        # Note: needs to be done after checking for car plugins, otherwise for agile a load of the candidate plan will be triggered as it thinks the car is charging
        if self.car_slots.empty:
            self.agile_car_plan_activated = 0
            self.tariff_reloaded = 0


        self._create_windows()

        self._create_ev_windows()

        
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

        self.status("Writing to HA")
        self._write_output()


        if self.get_config("read_only"):
            self.log("Read only mode enabled. Not querying inverter.")
            self.status("Idle (Read Only)")

            # Set the EV charger entity, even if in ReadOnly
            ### For code development only - allows test of EV charger whilst not interferring with inverter. Remove when code development complete.
            self._control_EV_charger()
            self.log("")

        else:

            # Get the current status of the inverter
            did_something = True
            self.status("Updating Inverter")

            #self.log("")
            #entity_id = self.config[f"id_timed_charge_current"]
            #self.log(self.get_state_retry(entity_id))
            ##End logging

            inverter_update_count = 0
            while did_something and inverter_update_count < MAX_INVERTER_UPDATES:
                inverter_update_count += 1

                status = self.inverter.status
                self._log_inverterstatus(status)

                time_to_slot_start = (self.charge_start_datetime - pd.Timestamp.now(self.tz)).total_seconds() / 60
                time_to_slot_end = (self.charge_end_datetime - pd.Timestamp.now(self.tz)).total_seconds() / 60

                # if len(self.windows) > 0:
                if (
                    (time_to_slot_start > 0)
                    and (time_to_slot_start < self.get_config("optimise_frequency_minutes"))
                    and (len(self.windows) > 0)
                ) or (self.get_config("id_battery_soc") < self.get_config("sleep_soc")):
                    # Next slot starts before the next optimiser run. This implies we are not currently in
                    # a charge or discharge slot

                    if self.get_config("id_battery_soc") < self.get_config("sleep_soc"):
                        self.log(
                            f"Current SOC of {self.get_config('id_battery_soc'):0.1f}% is less than battery_sleep SOC of {self.get_config('sleep_soc'):0.1f}%"
                        )
                    elif len(self.windows) > 0:
                        self.log(f"Next charge/discharge window starts in {time_to_slot_start:0.1f} minutes.")
                    else:
                        self.log("No charge/discharge windows planned.")

                    if self.charge_power > 1:
                        self.log("Charge Power >1")
                        self.inverter.control_discharge(enable=False)

                        self.inverter.control_charge(
                            enable=True,
                            start=self.charge_start_datetime,
                            end=self.charge_end_datetime,
                            power=self.charge_power,
                            target_soc=self.charge_target_soc,
                        )

                    elif self.charge_power < 0:
                        self.log("Charge Power <0")
                        self.inverter.control_charge(enable=False)

                        self.inverter.control_discharge(
                            enable=True,
                            start=self.charge_start_datetime,
                            end=self.charge_end_datetime,
                            power=self.charge_power,
                            target_soc=self.charge_target_soc,
                        )
                    # For IOG hold slots, so they don't write to the inverter all night
                    # This however will not pickup normal hold slots "<=", they are dealt with below when actually within a hold period.
                    
                    elif (self.charge_power == 1) & (self.windows["hold_soc"].iloc[0] == "<=Car"):
                        self.log("Car slot")
                        self.inverter.control_discharge(enable=False)

                        self.inverter.control_charge(
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
                    self.log("Currently in charge/discharge/hold slot")

                    # If the current slot is a Hold SOC slot and we aren't holding then we need to
                    # enable Hold SOC. Uses backup mode instead of charge current = 0 to allow excess solar to charge batteries.


                    if (
                        self.hold and self.hold[0]["active"]
                    ):  # Should not activate for Car slots (as self.hold shouldnt be active)

                        self.log("In a hold slot")
                        self.log("Printing Status")
                        self.log("")
                        self.log(status)  # This is the inverter status
                        self.log("")
                        self.log(self.hold)  # Two elements, active (true/false) and SOC (value)
                        self.log(self.hold[0]["soc"])  # SOC value stored in first row of self.hold
                        self.log(status["hold_soc"]["active"])  # What the inverter thinks its doing
                        self.log(status["hold_soc"]["soc"])  # The value of backup_soc last read from the inverter.

                        # If status is not hold OR the inverter SOC value isnt matching the required SOC hold value
                        if (
                            not status["hold_soc"]["active"] or status["hold_soc"]["soc"] != self.hold[0]["soc"]
                        ):  #  not sure what this line will report
                            self.log("....but status is not hold")
                            self.log(f"  Enabling SOC hold at SOC of {self.hold[0]['soc']:0.0f}%")
                            self.inverter.hold_soc_old(enable=True, soc=self.hold[0]["soc"])

                        else:
                            self.log(f"  Inverter already holding SOC of {self.hold[0]['soc']:0.0f}%")

                    else:  # if already in Car slot, this bit should run
                        self.log(f"Current charge/discharge window ends in {time_to_slot_end:0.1f} minutes.")

                        if self.charge_power > 0:  # Intentionally 0 (not 1) to ensure Car slots are also encompassed.
                            if not status["charge"]["active"]:
                                self.log("Charge status is not active, setting start time value now")
                                start = pd.Timestamp.now(tz=self.tz)
                            else:
                                self.log("Charge status is active, not setting start time")
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
                    if self.charge_power > 0:  # for charge slots and Car hold slots
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
                        str_log += " but discharge start and end times are different."
                        self.log(str_log)
                        self.inverter.control_discharge(enable=False)
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
                            str_log += " but inverter has a charge slot before then. Disabling charge."
                            self.log(str_log)
                            self.inverter.control_charge(enable=False)
                            did_something = True

                    if status["hold_soc"]["active"]:
                        self.inverter.hold_soc_old(enable=False)
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
                            self.status(f"Waiting for inverter Read cycle: {i}")
                            time.sleep(1)
                            i -= 1

                        # status = self.inverter.status
                        # self._log_inverterstatus(status)

            status_switches = {
                "charge": "off",
                "discharge": "off",
                "hold_soc": "off",
            }

            if status["hold_soc"]["active"]:
                self.status(f"Holding SOC at {status['hold_soc']['soc']:0.0f}%")
                status_switches["hold_soc"] = "on"

            elif status["charge"]["active"]:
                self.status("Charging")
                status_switches["charge"] = "on"

            elif status["discharge"]["active"]:
                self.status("Discharging")
                status_switches["discharge"] = "on"

            else:
                self.status("Idle")

            for switch in status_switches:
                service = f"switch/turn_{status_switches[switch]}"
                entity_id = f"switch.{self.prefix}_{switch}_active"
                self.call_service(
                    service=service,
                    entity_id=entity_id,
                )

            # Inverter updates complete. Now command EV charger on/off. 
            self._control_EV_charger()
            self.log("")

    def _create_windows(self):

        # If we are already in the first slot (e.g. 10 mins in or 20 mins in) then the value of "forced" is factored so I think .flows calculations continue to work for 20 and then 10 mins remaining.
        # However, a factored "forced" value means that it result in a seperate charge window for the remaining time, and for IOG/IO/E7 that will result in needless
        # writes to the inverter every 10 minutes and an increasing charge power towards the end of the night to compensate.
        # As the .flows calls are all done with now, the "forced" power can be set back to what the inverter needs it to be, which is the original value prior to factoring

        # Get the time of the first slot
        #self.opt["start"] = self.opt.index.tz_convert(self.tz)
        #self.charge_start_datetime = self.opt["start"].iloc[0]

        #slot_left_factor = 0

        # Are we already partway through that slot?
        #if pd.Timestamp.now(self.tz) > self.charge_start_datetime:
        #    slot_left_factor = 1800 / (
        #        (self.charge_start_datetime + pd.Timedelta(30, "minutes") - pd.Timestamp.now(self.tz)).total_seconds()
        #    )

        # If we are in a slot, then "forced" has already been factored by the slot time remaining to ensure the power flow calclations are correct
        # We need to remove that factor so the inverter charge power remains unchanged in the slot.
        # If forced = 0 (i.e no charging) the result remains zero so no need to gate with forced > 0.

        # SVB this needs a "not to exceed" limit to:
        # 1) Handle large multiplication factors for programme restarts at time values very close to the half hour boundaries. Just limit to 6. DONE
        # 2) To handle slots that even when factored, are still limited by the inverter power - these ones we don't want to multiply.

        # In 2), is it just a limit of charger power we need to apply? Or do we require something more complex? 

        #if not slot_left_factor == 0:
        #    if slot_left_factor > 6:
        #        slot_left_factor = 6
        #    self.opt["forced"].iloc[0] = self.opt["forced"].iloc[0] * slot_left_factor
        

        # SVB Previous code created a seperate period if the power stored in "forced" differed between rows (1/2 hour slots) by anything bigger than 0.
        # On IOG, as all high cost swaps are shared equally between the 12 1/2 hour slots, we only need a small rounding error for the value of "forced" to end up different
        # and thus generate a new charge window. This rounding error equally applies to the restoration of the forced value prior to factoring. This "">0" test
        # almost guarantees an IOG 6 hour charge window to end up as one hold slot after another, rather than what should be a 6 hour charge slot at a fixed charge rate.

        # Now changed this so its based on the value of forced_power_group_tolerance (currently set to 100W), say half of it (50W).

        tolerance = self.get_config("forced_power_group_tolerance")

        # Increment "period" if charge power varies by more than half the power tolerance OR non-contiguous car slot detected (when charge power = 0).

        self.opt["period"] = (
            (self.opt["forced"].diff() > (tolerance / 2))
            | ((self.opt["carslot"].diff() > 0) & (self.opt["forced"] == 0))
        ).cumsum()

        if self.debug and "O" in self.debug_cat:
            self.log("")                
            self.ulog("1/2 Hour Optimsation summary")
            self.log(f"\n{self.opt.to_string()}")

        if self.debug and "W" in self.debug_cat:
            self.log("")
            self.ulog("Debugging - Charge/Discharge/Hold Windows")
            self.log("")

        # If there is either a charge/discharge plan or a car charging plan, create windows.
        if ((self.opt["forced"] != 0).sum() > 0) or ((self.opt["carslot"] != 0).sum() > 0):
            x = self.opt[self.opt["forced"] > 0].copy()
            x["start"] = x.index.tz_convert(self.tz)
            x["end"] = x.index.tz_convert(self.tz) + pd.Timedelta(30, "minutes")
            x["soc"] = x["soc"].round(0).astype(int)
            x["soc_end"] = x["soc_end"].round(0).astype(int)

            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing X for charge slots.....")
                # self.log(x.to_string())
                self.log(f"\n{x.to_string()}")


            # Create the charge window by taking the first and the last entry for each period.
            windows_c = pd.concat(
                [
                    x.groupby("period").first()[["start", "soc", "forced"]],
                    x.groupby("period").last()[["end", "soc_end"]],
                ],
                axis=1,
            )

            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing Window_C for charge")
                self.log(f"\n{windows_c.to_string()}")
                # self.log(windows_c.to_string())

            x = self.opt[self.opt["forced"] < 0].copy()
            x["start"] = x.index.tz_convert(self.tz)
            x["end"] = x.index.tz_convert(self.tz) + pd.Timedelta(30, "minutes")

            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing X for discharge slots.....")
                self.log(f"\n{x.to_string()}")


            windows_d = pd.concat(
                [
                    x.groupby("period").first()[["start", "soc", "forced"]],
                    x.groupby("period").last()[["end", "soc_end"]],
                ],
                axis=1,
            )

            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing Window_D for discharge")
                self.log(f"\n{windows_d.to_string()}")

            # Combine charge and discharge windows
            self.windows = pd.concat([windows_c, windows_d]).sort_values("start")

            # Create a Hold slot for all car slots
            x = self.opt[self.opt["carslot"] == 1].copy()
            x["start"] = x.index.tz_convert(self.tz)
            x["end"] = x.index.tz_convert(self.tz) + pd.Timedelta(30, "minutes")

            # Delete any entries where charging is already scheduled (Forced > 1)
            x = x.drop(x[x["forced"] > 1].index)

            # Set "forced" to 1 on the remainder, if Zappi is seen as part of house load)
            if self.get_config("ev_part_of_house_load"):
                x["forced"] = 1

            # Set "forced" to 1 on the remainder, if Prevent_Discharge is set)
            if self.get_config("prevent_discharge"):
                x["forced"] = 1

            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing X for Car Hold slots (if not already charging)")
                self.log("")
                self.log(f"\n{x.to_string()}")
                # self.log(x.to_string())

            # Create the window by taking the first and the last entry for each period.

            windows_car = pd.concat(
                [
                    x.groupby("period").first()[["start", "soc", "forced"]],
                    x.groupby("period").last()[["end", "soc_end"]],
                ],
                axis=1,
            )


            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing Window_car for Car slots")
                self.log(f"\n{windows_car.to_string()}")

 
            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing Combined Window for Charge and Discharge Slots")

                self.log(f"\n{self.windows.to_string()}")
                # self.log(self.windows.to_string())

            self.windows["hold_soc"] = ""

            tolerance = self.get_config("forced_power_group_tolerance")
            if tolerance > 0:
                self.windows["forced"] = ((self.windows["forced"] / tolerance).round(0) * tolerance).astype(int)

            if self.debug and "X" in self.debug_cat:
                self.log("")
                self.log("Printing Combined Window after power rounding")
                self.log(f"\n{self.windows.to_string()}")

            # Add the Car slots. This is done after power value rounding to ensure the Forced = 1 setting remains
            self.windows = pd.concat([windows_car, self.windows]).sort_values("start")

            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Printing Combined Window after concatenation.....")
                self.log(f"\n{self.windows.to_string()}")

            # Round SOC to integers
            self.windows["soc"] = self.windows["soc"].round(0).astype(int)
            self.windows["soc_end"] = self.windows["soc_end"].round(0).astype(int)
            self.windows["hold_soc"] = ""

            if self.config["supports_hold_soc"]:

                if self.debug and "W" in self.debug_cat:
                    self.log("")
                    self.log("Checking for Hold SOC slots (SOC changes less than 3%)")


                self.windows.loc[
                    ((self.windows["soc_end"] - self.windows["soc"]).abs() < HOLD_TOLERANCE)
                    & (
                        self.windows["soc"] > self.get_config("maximum_dod_percent")
                    ),  # What is this line for? Why prevent setting a hold if on minimum SOC?
                    "hold_soc",
                ] = "<="

                if self.debug and "W" in self.debug_cat:
                    self.log("")
                    self.log("Printing Combined Window after Hold SOC check.....")
                    self.log(f"\n{self.windows.to_string()}")

            ### Need to add Agile tariff into this, but only if car charging is enabled (EV Charger = Zappi?) 
            #   DONE needs verifying
            
            #if self.intelligent or (self.agile and self.ev) :  # gate removed******
            if self.debug and "W" in self.debug_cat:
                self.log("")
                self.log("Setting Car slots (Forced = 1) to hold")  

            # If forced = 1 then the window is an Car Slot. It will already have a "<=" set as we made start SOC = end SOC, but we
            # possibly want to differentiate the two for later processing.
            self.windows.loc[
                (self.windows["forced"] == 1),
                "hold_soc",
            ] = "<=Car"

            # Set soc end to equal start soc for any car slots (Forced = 1) (purely for dashboard display purposes)
            self.windows["soc_end"] = self.windows["soc_end"].where(self.windows["forced"] != 1, self.windows["soc"])
            #end of gate removed******

            if self.debug and "W" in self.debug_cat:

                self.log("")
                self.log("Printing Combined Window after <=Car added for any Car slots.....")
                self.log(f"\n{self.windows.to_string()}")

            self.log("")
            self.log("Optimal forced charge/discharge slots:")
            for window in self.windows.iterrows():
                self.log(
                    f"  {window[1]['start'].strftime('%d-%b %H:%M %Z'):>13s} - {window[1]['end'].strftime('%d-%b %H:%M %Z'):<13s}  Power: {window[1]['forced']:5.0f}W  SOC: {window[1]['soc']:4d}% -> {window[1]['soc_end']:4d}%  {window[1]['hold_soc']}"
                )

            self.charge_start_datetime = self.windows["start"].iloc[0].tz_convert(self.tz)
            self.charge_end_datetime = self.windows["end"].iloc[0].tz_convert(self.tz)

            self.charge_power = self.windows["forced"].iloc[0]
            voltage = self.get_config("battery_voltage", default=50)
            if voltage > 0 and not self.charge_power == 1:
                self.charge_current = self.charge_power / voltage
            elif voltage > 0 and self.charge_power == 1:
                self.charge_current = 0.1  # Set a non-zero charge current so Car slots are seen as charge slots (to make use of start and stop times)
            else:
                self.charge_current = None
            self.charge_target_soc = self.windows["soc_end"].iloc[0]

            # Flag hold for "<=" (SOC less then 3%) but not Car slots

            self.hold = [
                {
                    # "active": (self.windows["hold_soc"].iloc[i] == "<=") or (self.windows["hold_soc"].iloc[i] == "<=Car"),
                    "active": (self.windows["hold_soc"].iloc[i] == "<="),
                    "soc": self.windows["soc_end"].iloc[i],
                }
                for i in range(0, min(len(self.windows), 1))
            ]

            if self.debug and "X" in self.debug_cat:
                self.log("Printing final result of _create_windows....")
                self.log("Charge_start_datetime = ")
                self.log(self.charge_start_datetime)
                self.log("Charge_end_datetime = ")
                self.log(self.charge_end_datetime)
                self.log("Charge_target_soc = ")
                self.log(self.charge_target_soc)
                self.log("Hold = ")
                self.log(self.hold)

        else:
            self.log(f"No charging slots")
            self.charge_current = 0
            self.charge_power = 0
            self.charge_target_soc = 0
            self.charge_start_datetime = self.static.index[0].tz_convert(self.tz)
            self.charge_end_datetime = self.static.index[0].tz_convert(self.tz)
            self.hold = []
            self.windows = pd.DataFrame()

    def _create_ev_windows(self):
        
        # At the moment the only purpose of this routine is for dashboard display (in the future)
        # Actual charging is done by reading self.opt

        # Clear "period" to 0 (as period was previously set i.a.w. house battery charging)
        self.opt["period"] = 0

        # Increment "period" if non-contiguous car slot detected.
        self.opt["period"] = (
            (self.opt["carslot"].diff() > 0)
        ).cumsum()

        if ((self.opt["carslot"] != 0).sum() > 0):
            x = self.opt[self.opt["carslot"] > 0].copy()
            x["start"] = x.index.tz_convert(self.tz)
            x["end"] = x.index.tz_convert(self.tz) + pd.Timedelta(30, "minutes")

            # Create the EV charge windows by taking the first and the last entry for each period.
            ev_windows = pd.concat(
               [
                   x.groupby("period").first()[["start"]],
                   x.groupby("period").last()[["end"]],
               ],
               axis=1,
            )

            ### SVB to do
            # Add a "Average slot price" and a "total kWh" to each window

            if self.debug and "E" in self.debug_cat:
                self.log("")      
                self.log("EV Windows are")
                self.log(f"\n{ev_windows.to_string()}")

            self.ev_windows = ev_windows

            self.log("")
            self.log("Optimal EV charging slots:")
            for window in self.ev_windows.iterrows():
                self.log(
                    #f"  {window[1]['start'].strftime('%d-%b %H:%M %Z'):>13s} - {window[1]['end'].strftime('%d-%b %H:%M %Z'):<13s}  Power: {window[1]['forced']:5.0f}W  SOC: {window[1]['soc']:4d}% -> {window[1]['soc_end']:4d}%  {window[1]['hold_soc']}"
                    f"  {window[1]['start'].strftime('%d-%b %H:%M %Z'):>13s} - {window[1]['end'].strftime('%d-%b %H:%M %Z'):<13s}"
                )

    def _log_inverterstatus(self, status):
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
        attributes={},
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
            | attributes
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
            attributes={"Summary": self.summary_costs},
        )

        if len(self.windows) > 0:
            hass_start = self.charge_start_datetime
            hass_end = self.charge_end_datetime
        else:
            hass_start = pd.Timestamp.now().floor("1D")
            hass_end = hass_start

        self.write_to_hass(
            entity=f"sensor.{self.prefix}_charge_start",
            state=hass_start,
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

        if len(self.car_slots) > 0:
            io_slot_datetime = self.car_slots["start_dt"].iloc[0].tz_convert(self.tz)
        else:
            io_slot_datetime = self.static.index[0].tz_convert(self.tz)

        attributes = (
            {
                "friendly_name": "Pv Opt Candidate Car Charging Slots",
                "device_class": "timestamp",
                "windows": [
                    {
                        k: window1[1][k]
                        for k in [
                            "start_local",
                            "end_local",
                            "charge_in_kwh",
                            "import",
                        ]
                    }
                    for window1 in self.candidate_car_slots.iterrows()
                ],
            }
            | {"ev_total_charge": self.candidate_ev_total_charge}
            | {"ev_total_cost": self.candidate_ev_total_cost}
            | {"ev_percent_to_add": self.candidate_ev_percent_to_add}
        ) 

        self.write_to_hass(
            entity=f"sensor.{self.prefix}_candidate_car_slots",
            state=io_slot_datetime,
            attributes=attributes,
        )

        attributes = (
            {
                "friendly_name": "Pv Opt Car Charging Slots",
                "device_class": "timestamp",
                "windows": [
                    {
                        k: window1[1][k]
                        for k in [
                            "start_local",
                            "end_local",
                            "charge_in_kwh",
                            "import",
                        ]
                    }
                    for window1 in self.car_slots.iterrows()
                ],
            }
            | {"ev_total_charge": self.ev_total_charge}
            | {"ev_total_cost": self.ev_total_cost}
            | {"ev_percent_to_add": self.ev_percent_to_add}
            | {"ev_car_slots_last_loaded": self.car_slots_last_loaded}
        ) 

        self.write_to_hass(
            entity=f"sensor.{self.prefix}_car_slots",
            state=io_slot_datetime,
            attributes=attributes,
        )

        attributes = (
            {
                "friendly_name": "Pv Opt Car Charging Windows",
                "device_class": "timestamp",
                "windows": [
                    {
                        k: window1[1][k]
                        for k in [
                            "start",
                            "end",
                        ]
                    }
                    for window1 in self.ev_windows.iterrows()
                ],
            }
            | {"ev_total_charge": self.ev_total_charge}
            | {"ev_total_cost": self.ev_total_cost}
            | {"ev_percent_to_add": self.ev_percent_to_add}
            | {"ev_car_slots_last_loaded": self.car_slots_last_loaded}
        ) 

        self.write_to_hass(
            entity=f"sensor.{self.prefix}_car_windows",
            state=io_slot_datetime,
            attributes=attributes,
        )


        self.write_to_hass(
            entity=f"sensor.{self.prefix}_charge_end",
            state=hass_end,
            attributes={
                "friendly_name": "PV Opt Next Charge Period End",
            },
        )
        if self.charge_current is not None:
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


        if self.intelligent:
            tariff = "intelligent"
        elif self.agile:
            tariff = "agile"
        else:
            tariff = "other"        


        self.write_to_hass(
            entity=f"sensor.{self.prefix}_tariff",
            state=tariff,
            attributes={
                "friendly_name": "PV Opt Tariff",
            },
        )


    def load_solcast(self):
        if not self.get_config("use_solar", True):
            df = pd.DataFrame(
                index=pd.date_range(pd.Timestamp.now(tz="UTC").normalize(), periods=96, freq="30min"),
                data={"Solcast": 0, "Solcast_p10": 0, "Solcast_p90": 0, "weighted": 0},
            )
            return df

        if self.debug and "X" in self.debug_cat:
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

            if self.debug and "P" in self.debug_cat:
                self.log(f"kWh data from {entity_id} is")
                self.log(f"\n{df.to_string()}")

            df.index = pd.to_datetime(df.index)
            x = df.diff().clip(0).fillna(0).cumsum() + df.iloc[0]
            x.index = x.index.round("1s")
            x = x[~x.index.duplicated()]
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
        index = pd.date_range(start, end, inclusive="left", freq="30min")
        consumption = pd.DataFrame(index=index, data={"consumption": 0})

        if self.get_config("use_consumption_history"):
            time_now = pd.Timestamp.now(tz="UTC")
            if (start < time_now) and (end < time_now):
                self.log("  - Start and end are both in past so actuals will be used with no weighting")
                days = (time_now - start).days + 1
            else:
                days = int(self.get_config("consumption_history_days"))

            df = None

            entity_ids = []
            entity_id = None

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

            for entity_id in entity_ids:
                power = self.hass2df(entity_id=entity_id, days=days)
                self.log(f"Getting consumption in W from: {entity_id} ")
                power = self.riemann_avg(power)
                if df is None:
                    df = power
                else:
                    df += power

            if df is None:
                self.log(f"Getting consumption in kWh from: {entity_id} ")
                df = self._get_hass_power_from_daily_kwh(
                    entity_id,
                    days=days,
                    log=self.debug,
                )
                if self.debug and "P" in self.debug_cat:
                    self.log("Df after first load is:......")
                    self.log(df.to_string())

            if df is None:
                self.status("ERROR: No consumption history.")
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
                self.status(f"WARNING: Consumption < {days} days.")
                str_days = "Potential error. <<<"

            self.log(f"  - {days} days was expected. {str_days}")


            if (len(self.zappi_consumption_entities) > 0) and self.ev:
                self.log("Getting consumption in kWh from Zappi Charger(s)")
                ev_power = self._get_zappi(start=df.index[0], end=df.index[-1], log=True)
                if len(ev_power) > 0:
                    self.log("")
                    self.log(
                        f"    EV consumption from    {ev_power.index[0].strftime(DATE_TIME_FORMAT_SHORT)} to {ev_power.index[-1].strftime(DATE_TIME_FORMAT_SHORT)} is {(ev_power.sum()/2000):0.1f} kWh"
                    )
                    self.log(
                        f"    Total consumption from {df.index[0].strftime(DATE_TIME_FORMAT_SHORT)} to {df.index[-1].strftime(DATE_TIME_FORMAT_SHORT)} is {(df.sum()/2000):0.1f} kWh"
                    )

                else:
                    self.log("")
                    self.log("  No power returned from Zappi(s)")

            if (start < time_now) and (end < time_now):
                consumption["consumption"] = df.loc[start:end]
            else:
                if self.ev:
                    df_EV = None  # To store EV consumption
                    df_EV_Total = None  # To store EV consumption and Total consumption
                    dfx = None

                    if self.get_config("ev_part_of_house_load"):
                        self.log(
                            "    EV charger is seen as house load, so subtracting EV charging from Total consumption"
                        )
                        df_EV_Total = pd.concat(
                            [ev_power, df], axis=1
                        )  # concatenate total consumption and ev consumption into a single dataframe (as they are different lengths)
                        df_EV_Total.columns = ["EV", "Total"]  # Set column names
                        df_EV_Total = df_EV_Total.fillna(0)  # fill any missing values with 0

                        df_EV = df_EV_Total["EV"].squeeze()  # Extract EV consumption to Series
                        df_Total = df_EV_Total["Total"].squeeze()  # Extract total consumption to Series
                        df = df_Total - df_EV  # Substract EV consumption from Total Consumption

                        if self.debug and "Q" in self.debug_cat:
                            self.log("Result of subtraction is")
                            self.log(df.to_string())

                        if (df < 0).any().any():  # Are there any negative values in the subtraction?
                            self.log("    Unexpected Negative values after substraction found, setting to zero")
                            df[df < 0] = 0

                # Add consumption margin
                df = df * (1 + self.get_config("consumption_margin") / 100)
                if self.debug and "Q" in self.debug_cat:
                    self.log("Df after adding consumption margin is.......")
                    self.log(df.to_string())

                dfx = pd.Series(index=df.index, data=df.to_list())

                # Group by time and take the mean
                df = df.groupby(df.index.time).aggregate(self.get_config("consumption_grouping"))
                df.name = "consumption"

                if self.debug and "Q" in self.debug_cat:
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
                        self.log(f">>> dow : {len(consumption_dow)}")
                        self.log(f">>> mean: {len(consumption_mean)}")
                        idx = consumption_dow.index.intersection(consumption_mean.index)
                        self.log(f"Clipping the consumption to the overlap ({len(idx)/24:0.1f} days)", level="WARNING")
                        consumption_mean = consumption_mean.loc[idx]
                        consumption_dow = consumption_dow.loc[idx]

                    consumption["consumption"] += pd.Series(
                        consumption_dow.to_numpy()
                        + consumption_mean.to_numpy() * (1 - self.get_config("day_of_week_weighting")),
                        index=consumption_mean.index,
                    )
                else:
                    self.log(f"  - Ignoring 'Day of Week Weighting' because only {days} days of history is available")
                    consumption["consumption"] = consumption_mean

            if len(entity_ids) > 0:
                self.log(f"    Estimated consumption from {entity_ids} loaded OK ")

            else:
                self.log(f"    Estimated consumption from {entity_id} loaded OK ")

        else:
            daily_kwh = self.get_config("daily_consumption_kwh")
            self.log(f"  - Creating consumption based on daily estimate of {daily_kwh} kWh")

            if self.get_config("shape_consumption_profile"):
                self.log("    and typical usage profile.")
                daily = (
                    pd.DataFrame(self.get_config("consumption_shape"))
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

        self.log("")


        ### This next section prints a consumption based on two days worth, as predicted from the last 7 days
        # What we want is a predicted consumption for the next day, so we can compare it to fixed consumption
        # problems: 
        # Not sure where two days is created from  (as df is definitley one day)
        # Each of the two days has different, so its not a straight double generated from the one day df

        self.log(
            f"    Total consumption from {consumption.index[0].strftime(DATE_TIME_FORMAT_SHORT)} to {consumption.index[-1].strftime(DATE_TIME_FORMAT_SHORT)}:"
        )
        self.log(f"    Total consumption: {(consumption['consumption'].sum() / 2000):0.1f} kWh")



        if self.debug and "P" in self.debug_cat:
            self.log("Printing final result of routine load_consumption.....")
            self.log(consumption.to_string())
        return consumption

    def _auto_cal(self):
        self.ulog("Calibrating PV System Model")
        end = pd.Timestamp.now(tz="UTC").normalize()
        start = end - pd.Timedelta(24, "hours")

        solar = self._get_solar(start, end)
        consumption = self.load_consumption(start, end)
        grid = self.load_grid(start, end)
        soc = self.hass2df(self.config["id_battery_soc"], days=2, freq="30min").loc[start:end]

    def load_grid(self, start, end):
        self.log(
            f"Getting yesterday's grid flows ({start.strftime(DATE_TIME_FORMAT_SHORT)} - {end.strftime(DATE_TIME_FORMAT_SHORT)}):"
        )
        # entity_id = self.config["id_daily_solar"]
        mults = {"id_grid_import_power": 1, "id_grid_import_power": -1, "id_grid_power": 1}
        days = (pd.Timestamp.now(tz="UTC") - start).days + 1
        mults = {mults[id] for id in mults if id in self.config}
        for id in mults:
            entity_id = self.config[id]
            if self.entity_exists(entity_id):
                x = self.hass2df(entity_id, days=days)
                if x is not None:
                    x = (self.riemann_avg(x).loc[start : end - pd.Timedelta("30min")] / 10).round(0) * 10 * mults[id]
                    if df is None:
                        df = x
                    else:
                        df += x
                else:
                    self.log("  - FAILED")
            self.log("")
        return df

    def _compare_tariffs(self):
        self.status("Comparing Tariffs")
        self.ulog("Comparing yesterday's tariffs")
        end = pd.Timestamp.now(tz="UTC").normalize()
        start = end - pd.Timedelta(24, "hours")
        self.io_prices = {}

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

        if self.debug and "T" in self.debug_cat:
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

            opt["period_start"] = opt.index.tz_convert(self.tz).strftime("%Y-%m-%dT%H:%M:%S%z").str[:-2] + ":00"

            attributes = {
                "state_class": "measurement",
                "device_class": "monetary",
                "unit_of_measurement": "GBP",
                "friendly_name": f"PV Opt Comparison {contract.name}",
                "net_base": round(net_base.sum() / 100, 2),
            } | {col: opt[["period_start", col]].to_dict("records") for col in cols if col in opt.columns}

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
        entity_ids = self.config["id_solar_power"]
        if not isinstance(entity_ids, list):
            entity_ids = [entity_ids]

        df = None
        days = (pd.Timestamp.now(tz="UTC") - start).days + 1

        for entity_id in entity_ids:
            if self.entity_exists(entity_id):
                x = self.hass2df(entity_id, days=days)
                if x is not None:
                    x = (self.riemann_avg(x).loc[start : end - pd.Timedelta("30min")] / 10).round(0) * 10
                    if df is None:
                        df = x
                    else:
                        df += x
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
                # SVB debugging
                # self.log("")
                # self.log("Entity name to be read is .....")
                # self.log(self.bottlecap_entities[direction])
                # self.log("")
                # x = pd.DataFrame(
                #    self.get_state_retry(self.bottlecap_entities[direction], attribute=("rates"))
                # )
                # self.log("")
                # self.log("Read of Bottlecap rates entities is.....")
                # self.log(x.to_string())

                df = pd.DataFrame(
                    self.get_state_retry(self.bottlecap_entities[direction], attribute=("rates"))
                ).set_index("start")["value_inc_vat"]
                df.index = pd.to_datetime(df.index, utc=True)
                df *= 100

                ## SVB logging
                # self.log("Printing Bottlecap Dave load converted to df")
                # self.log(df.to_string())

                df = pd.concat(
                    [
                        df,
                        self.contract.tariffs[direction].to_df(start=df.index[0], end=df.index[-1], day_ahead=False)[
                            "unit"
                        ],
                    ],
                    axis=1,
                ).set_axis(["bottlecap", "pv_opt"], axis=1)

                # SVB logging
                # self.log("Printing contract comparison df")
                # self.log(df.to_string())

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
                    self.status("ERROR: Tariff inconsistency")
                    err = True

            self.log(f"  {direction.title()}: {str_log}")

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

            states = {k: states[k] for k in states if (self.device_name) in k}
            #states = {k: states[k] for k in states if self.device_name in k or "zappi" in k}  # : print zappi entities as well
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
            self.rlog(f"    >>> Getting {days} days' history for {entity_id}")
            self.log(f"    >>> Entity exists: {self.entity_exists(entity_id)}")

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

    def write_and_poll_time(self, entity_id, value):
        changed = False
        written = False

        # Set consistent date for all comparisons
        value = value.replace(year=2024, month=1, day=1)
        
        old_time = pd.to_datetime("2024/01/01 " + self.get_state_retry(entity_id=entity_id))
        new_time = None

        #self.log(f"Write_and_poll_time: time = {value}, old_time = {old_time}")
        
        #Convert time to string of HH:MM:SS for call_service routine
        value_str = value.strftime('%X')

        if old_time != value:
            changed = True
            #self.log(f"Write_and_poll_time: Changed = true")

            try:
                #self.call_service("number/set_value", entity_id=entity_id, value=value)
                self.call_service("time/set_value", entity_id=entity_id, time=value_str)

                written = False
                retries = 0
                while not written and retries < WRITE_POLL_RETRIES:
                    #self.log("Write_and_poll_time: Entered while loop")
                    retries += 1
                    time.sleep(WRITE_POLL_TIME_SLEEP)

                    new_time = pd.to_datetime("2024/01/01 " + self.get_state_retry(entity_id=entity_id))
                    
                    #self.log(f"Write_and_poll_time:  while loop, new_time = {new_time}")

                    written = new_time == value

            except:
                written = False
                #self.log("Write_and_poll_time: Exception logged")

            str_log = f"Entity: {entity_id} Time: {value}  Value_str: {value_str}  Old Time: {old_time} New time: {(new_time)} "
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

        if not valid_state and "entity_id" in kwargs:
            # try:
            #     state = self.get_entity_default(kwargs.get("entity_id"))
            #     self.log(f"  - Using default value of {state}")
            # except:
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

    def get_item_from_entity(self, entity_id):
        item = entity_id.split(".")[-1]
        if item in DEFAULT_CONFIG:
            return item

    def get_entity_default(self, entity_id):
        item = self.get_item_from_entity(entity_id)
        if item is not None:
            return DEFAULT_CONFIG[item]["default"]


# %%
