# PV Opt: Home Assistant Solar/Battery Optimiser v4.0.6


Solar / Battery Charging Optimisation for Home Assistant. This appDaemon application attempts to optimise charging and discharging of a home solar/battery system to minimise cost electricity cost on a daily basis using freely available solar forecast data from SolCast. This is particularly beneficial for Octopus Agile but is also benefeficial for other time-of-use tariffs such as Octopus Flux or simple Economy 7.

The application will integrate fully with Solis inverters which are controlled using any of:

- [Home Assistant Solax Modbus Integration](https://github.com/wills106/homeassistant-solax-modbus) 
- [Home Assistant Core Modbus Integration](https://github.com/fboundy/ha_solis_modbus) 
- [Home Assistant Solis Sensor Integration](https://github.com/hultenvp/solis-sensor) 
- [Home Assistant Solarman Integration](https://github.com/davidrapan/ha-solarman) (1)

(1) https://github.com/StephanJoubert/home_assistant_solarman appears to be no longer maintained so has been replaced with
https://github.com/davidrapan/ha-solarman. This should be used for new installs for PvOpt v3.17.0 onwards.

Once installed it should require miminal configuration. Other inverters/integrations can be added if required or can be controlled indirectly using automations.

It has been tested primarily with Octopus tariffs but other tariffs can be manually implemented.

PV Opt supports EV charging:
 - If on Octopus Intelligent Go, PV Opt will incorporate any extra cheap slots in the house battery charge/discharge plan.
 - If on the Agile tariff, PV Opt can calculate a car charging plan which can be used to control your EV charger/car via external HA automation scripts.
 - If necessary Pv_opt automatically prevents house battery discharge during EV Charging.

<h2>Don't Buy Me a Beer or a Coffee...</h2>

Although I'm very partial to both, a better home for anything you might like to contribute would be the Mountain Rescue Team that I am currently a probationer (trainee) with. The Team comprises 40 unpaid volunteers and is on call 24/7 365 days a year in all weathers. You can donate via JustGiving by clicking on this link: 

   [![](https://images.justgiving.com/image/3857db4a-711b-4b08-8158-b6f4e1dbfa54.jpg?template=size200x200)](https://link.justgiving.com/v1/charity/donate/charityId/779549)

<h2>Pre-requisites</h2>

This app is not stand-alone it requires the following:

|| ||
|:----|:--|:--|
|<b><u>Websites |
| Solcast Hobby Account | Required | Provides solar PV generation forecasts up to 10 times per day,
| <b><u>Add-ons</b></u>|
|HACS| Required| Home Assistant Community Store - used to distribute the app and updates 
|AppDaemon | Required | Python execution environment
| Mosquitto MQTT Broker | Required | Used to create Home Assistant Entities using MQTT Discovery . 
| File Editor| Required | Used to edit the `appdaemon.yaml` and `config.yaml` files. Alternatively you could use `Samba Share` or `Studio Code Server`
| Samba Share| Alternative| Alternative to using File Editor to edit config files. Not convered in this guide.
| Studio Code Server| Alternative|Alternative to using `File Editor` to edit config files. Not convered in this guide.
| <u><b>Integrations</b></u> | | |
|Solcast PV Solar Integration | Required | Retrieves solar forecast from Solcast into Home Assistant. |
|Octopus Energy | Optional | Used to retrieve tariff information and Octopus Saving Session details. For users on Intelligent Octopus Go, this is required for any addtional slots outside of the 6 hour period to be taken into account in the charge/discharge plan. |
|Solax Modbus | Optional | Used to control Solis inverter directly. Support for two other integrations is now available (see below). Support inverter brands is possible using the API described below.
|MyEnergi | Optional | For Intelligent Octopus Go users using a Zappi charger, used by Pv_opt to detect EV plugin and supply EV consumption history. 

<h2>Step by Step Installation Guide</h2>

<h3>1. Get a Solcast Hobby Account</h3>

<b>PV_Opt</b> relies on solar forecasts data from Solcast. You can sign up for a Private User account [here](https://solcast.com/free-rooftop-solar-forecasting?gclid=CjwKCAiAr4GgBhBFEiwAgwORrQp6co5Qw8zNjEgUhBee7Hfa39_baEWG-rB-GB3FFpiaIA5eAPHhahoC3vAQAvD_BwE). This licence gives you 10 (it used to be 50 🙁) API calls a day.

<h3>2. Install HACS</h3>

1. Install HACS: https://hacs.xyz/docs/setup/download
2. Enable AppDaemon in HACS: https://hacs.xyz/docs/use/repositories/type/appdaemon/#making-appdaemon-apps-visible-in-hacs

<h3>3. Install the Solcast PV Solar Integration (v4.1.x)</h3>


1. Install the integation via HACS: https://github.com/BJReplay/ha-solcast-solar
2. Add the Integration via Settings: http://homeassistant.local:8123/config/integrations/dashboard
3. Once installed configure using your Solcast API Key from (1) . 
4. Set up an automation to update according to your desired schedule. Once every 3 hours will work.

<h3>4. Install the Octopus Energy Integration (If Required)</h3>



This excellent integration will pull Octopus Price data in to Home Assistant. Pv Opt pulls data from Octopus independently of this integration but will extract current tariff codes from it if they are avaiable. If not it will either use account details supplied in `secrets.yaml` or explicitly defined Octopus tariff codes set in `config.yaml`. If on Intelligent Octopus Go, this integration is required, as Pv_opt will use this to identify any slots allocated outside of 23:30 to 05:30 for use in its charge plan and managing the house battery during car charging slots. 


<h3>5. Install the Integration to Control Your Inverter</h3>

At present this app only works directly with Solis hybrid inverters using either the Solax Modbus integration (https://github.com/wills106/homeassistant-solax-modbus) or the HA Core Modbus as described here: https://github.com/fboundy/ha_solis_modbus, or combining the [Solis-Senor](https://github.com/hultenvp/solis-sensor) and [Solis-Control](https://github.com/hultenvp/solis_control) integrations.  
Support for the Solarman integrations (https://github.com/StephanJoubert/home_assistant_solarman and https://github.com/davidrapan/ha-solarman) are in test. 

<h4>Solax Modbus:</h4>

1. Install the integration via HACS: https://github.com/wills106/homeassistant-solax-modbus
2. Add the Integration via Settings: http://homeassistant.local:8123/config/integrations/dashboard
3. Configure the connection:
    |||
    |:--|:--|
    | Prefix| solis|
    |Interface| TCP/Ethernet|
    |Inverter Type| solis|
    |IP Address| IP of your datalogger|
    |TCP Port| 502|
    |Protocol| Modbus TCP|
4. Check that you have comms with the inverter and the various entities in the integration are populated with data

<h4>HA Core Modbus</h4>

Follow the Github instructions here: https://github.com/fboundy/ha_solis_modbus

<h4>Using Solis Cloud</h4>
<h5>Solis-Sensor</h5>

Follow the Github instruction here: https://github.com/hultenvp/solis-sensor

<h5>Solis-Control</h5>

Follow the Github instruction here: https://github.com/hultenvp/solis_control

<h4>Solarman</h4>

Follow the Github instructions here: (https://github.com/davidrapan/ha-solarman) 

For Solis Inverters, replace existing Solis_Hybrid.yaml with this one:

https://github.com/stevebuk1/pv_opt/blob/patch2/apps/pv_opt/solis_hybrid.yaml

Note:  installs using https://github.com/StephanJoubert/home_assistant_solarman have writes to the inverter disabled. For full inverter control, reinstall using the Solarman repo 
above.

<h3>6. Install the MQTT Integraion in Home Assistant</h3>

1. Click on the button below to add the MQTT integration:

    [![](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=mqtt)


<h3>7. Install Mosquitto MQTT Broker</h3>

1. Navigate to Settings -> Addons and click "Mosquito Broker"

2. Click on Install

3. Configure the Add-On as per the documentation: http://homeassistant.local:8123/hassio/addon/core_mosquitto/documentation

4. Either save the MQTT username and password in your `secrets.yaml` file or make a note of them for later.

<h3>8. Install File Editor</h3>

Follow instructions here: https://github.com/home-assistant/addons/blob/master/configurator/README.md

Navigate to Settings -> Addons -> File editor -> Configuration and set "Enforce Basepath" to "off".

<h3>9. Install Samba Share and/or Studio Code Server Add-ons If Required</h3>

Both of these add-ons make it easier to edit text files on your HA Install but aren't strictly necessary. `Samba Share` also makes it easier to access the AppDaemon log files.

<h3>10. Install AppDaemon</h3>

The <b>PV_Opt</b> python script currently runs under AppDaemon.

AppDaemon is a loosely coupled, multi-threaded, sandboxed python execution environment for writing automation apps for home automation projects, and any environment that requires a robust event driven architecture. The simplest way to install it on Home Assistantt is using the dedicated add-on:

1. Click the Home Assistant My button below to open the add-on on your Home Assistant instance:

   [![](https://camo.githubusercontent.com/a54868bd2c4edb2d623ab2fef3d074fe711b45c2c1cdc0fbe4dfd296faa594f8/68747470733a2f2f6d792e686f6d652d617373697374616e742e696f2f6261646765732f73757065727669736f725f6164646f6e2e737667)](https://my.home-assistant.io/redirect/supervisor_addon/?addon=a0d7b954_appdaemon&repository_url=https%3A%2F%2Fgithub.com%2Fhassio-addons%2Frepository)

2. Click on <b>Install</b>

3. Turn on <b>Auto update</b>

<h3>11. Configure AppDaemon</h3>

1. Use `File Editor` (or one of the alternatives) to open `/addon_configs/a0d7b954_appdaemon/appdaemon.yaml`.

2. The suggested configuration is as follows. This assumes that you are using `secrets.yaml` for your password information. If not then the `secrets` entry can be deleted and the `MQTT` `client_user` and `client password` will need to be entered explicitly.

        secrets: /homeassistant/secrets.yaml
        appdaemon:
          latitude: 54.729
          longitude: -2.991
          elevation: 175
          time_zone: Europe/London
          thread_duration_warning_threshold: 45
          app_dir: /homeassistant/appdaemon/apps
          plugins:
            HASS:
              type: hass
            MQTT:
              type: mqtt
              namespace: mqtt #
              verbose: True
              client_host: core-mosquitto
              client_port: 1883
              client_id: localad
              event_name: MQTT_MESSAGE 
              client_topics: NONE
              client_user: !secret mqtt-user
              client_password: !secret mqtt-password

        http:
          url: http://127.0.0.1:5050
        admin:
        api:
        hadashboard:

And add the `client_user` and `client_password` keys to `secrets.yaml` like this:

    mqtt-user: some_user
    mqtt-password: some_password
    
3. It is also recommended that you add the following entries to `appdaemon.yaml` to improve AppDaemon logging. These settings assume that you have a `/share/logs` folder setup using `Samba Share`.

        logs:
          main_log:
            filename: /share/logs/main.log
            date_format: '%H:%M:%S'
          error_log:
            filename: /share/logs/error.log
            date_format: '%H:%M:%S'    
          pv_opt_log:
            name: PV_Opt
            filename: /share/logs/pv_opt.log
            log_generations: 9
            log_size: 10000000
            date_format: '%H:%M:%S'      
            format: '{asctime} {levelname:>8s}: {message}'

5. Open the AppDaemon Add-On via Settings: http://homeassistant.local:8123/hassio/addon/a0d7b954_appdaemon/info

6. Click on <b>Configuration</b> at the top

7. Click the 3 dots and <b>Edit in YAML</b> to add `pandas` and `numpy` as Python packages. Note that `numpy` has to be set to version `1.26.4` due to an unresolved compatability issue between Home Assistant and `2.0.0`:

   ```
   init_commands: []
   python_packages:
     - pandas
     - numpy==1.26.4
   system_packages: []

   ```

8. Go back to the <b>Info</b> page and click on <b>Start</b>

9. Click on <b>Log</b>. Appdaemon will download and install numpy and pandas. Click on <b>Refresh</b> until you see:

   ```
    s6-rc: info: service init-appdaemon successfully started
    s6-rc: info: service appdaemon: starting
    s6-rc: info: service appdaemon successfully started
    s6-rc: info: service legacy-services: starting
    [12:54:30] INFO: Starting AppDaemon...
    s6-rc: info: service legacy-services successfully started
   ```

10. Either click on `Info` followed by `OPEN WEB UI` and then `Logs` or open your `main_log` file from the location specified in step (3) above. You should see:

    ```
    13:16:24 INFO AppDaemon: AppDaemon Version 4.4.2 starting
    13:16:24 INFO AppDaemon: Python version is 3.11.6
    13:16:24 INFO AppDaemon: Configuration read from: /config/appdaemon.yaml
    13:16:24 INFO AppDaemon: Added log: AppDaemon
    13:16:24 INFO AppDaemon: Added log: Error
    13:16:24 INFO AppDaemon: Added log: Access
    13:16:24 INFO AppDaemon: Added log: Diag
    13:16:24 INFO AppDaemon: Added log: PV_Opt
    13:16:25 INFO AppDaemon: Loading Plugin HASS using class HassPlugin from module hassplugin
    13:16:25 INFO HASS: HASS Plugin Initializing
    13:16:25 WARNING HASS: ha_url not found in HASS configuration - module not initialized
    13:16:25 INFO HASS: HASS Plugin initialization complete
    13:16:25 INFO AppDaemon: Loading Plugin MQTT using class MqttPlugin from module mqttplugin
    13:16:26 INFO MQTT: MQTT Plugin Initializing
    13:16:26 INFO MQTT: Using 'localad/status' as Will Topic
    13:16:26 INFO MQTT: Using 'localad/status' as Birth Topic
    13:16:26 INFO AppDaemon: Initializing HTTP
    13:16:26 INFO AppDaemon: Using 'ws' for event stream
    13:16:26 INFO AppDaemon: Starting API
    13:16:26 INFO AppDaemon: Starting Admin Interface
    13:16:26 INFO AppDaemon: Starting Dashboards
    13:16:26 INFO HASS: Connected to Home Assistant 2023.11.1
    13:16:26 INFO AppDaemon: Starting Apps with 0 workers and 0 pins
    13:16:26 INFO AppDaemon: Running on port 5050
    13:16:26 INFO MQTT: Connected to Broker at URL core-mosquitto:1883
    13:16:26 INFO AppDaemon: Got initial state from namespace mqtt
    13:16:26 INFO MQTT: MQTT Plugin initialization complete
    13:16:26 INFO HASS: Evaluating startup conditions
    13:16:26 INFO HASS: Startup condition met: hass state=RUNNING
    13:16:26 INFO HASS: All startup conditions met
    13:16:26 INFO AppDaemon: Got initial state from namespace default
    13:16:28 INFO AppDaemon: Scheduler running in realtime
    13:16:28 INFO AppDaemon: Adding /homeassistant/appdaemon/apps to module import path
    13:16:28 INFO AppDaemon: App initialization complete
    ```

That's it. AppDaemon is up and running. There is futher documentation for the on the [Add-on](https://github.com/hassio-addons/addon-appdaemon/blob/main/appdaemon/DOCS.md) and for [AppDaemon](https://appdaemon.readthedocs.io/en/latest/)


<h3>12. Install PV Opt from HACS</h3>

  0. Make sure HACS "Enable AppDaemon apps discovery & tracking" is enabled - under integrations in HA https://hacs.xyz/docs/categories/appdaemon_apps/
  1. Go to HACS
  2. Select `Automation`
  3. Click on the 3 dots top right and `Add Custom Repository`
  4. Add this repository https://github.com/fboundy/pv_opt and select `AppDaemon` as the `Category`
  5. Download the app

Once downloaded AppDaemon should see the app and attempt to load it using the default configuration. Go back to the AppDaemon logs and this time open pv_opt_log. You should see:

  ```
  16:53:23     INFO: ******************* PV Opt v3.19.0-Beta-17 *******************
  16:53:23     INFO: 
  16:53:23     INFO: Time Zone Offset: 0.0 minutes
  16:53:23     INFO: Reading arguments from YAML:
  16:53:23     INFO: -----------------------------------
  16:53:23     INFO: 
  16:53:23     INFO: Checking config:
  16:53:23     INFO: -----------------------
  16:53:23  WARNING:     forced_charge       = True   Source: system default. Not in YAML.
  16:53:23  WARNING:     forced_discharge    = True   Source: system default. Not in YAML.
  16:53:23  WARNING:     read_only           = True   Source: system default. Not in YAML.
  ```

<h3>13. Add an Automation to Restart AppDAemon when HA Restarts (Optional)</h3>

Restarts between Home Assistant and Add-Ons are not synchronised so it is helpful to set up an Automation to restart AppDAemon if HA is restarted. An example is shown below and included in this repo as `ha_restart_automation.yaml`. The `wait_template` section ensures that key integrations (in this case Solcast and Solax) have numeric values before AppDaemon is started.

    alias: Restart AppDaemon on HA Restart
    description: ""
    trigger:
      - event: start
        platform: homeassistant
    condition: []
    action:
      - service: hassio.addon_stop
        data:
          addon: a0d7b954_appdaemon
      - delay:
          hours: 0
          minutes: 1
          seconds: 0
          milliseconds: 0
      - wait_template: >
          {{(states('sensor.solcast_pv_forecast_forecast_today')| float(-1)>0) and
          (states('sensor.solis_battery_soc')| float(-1)>0)}}
        continue_on_timeout: true
      - service: hassio.addon_start
        data:
          addon: a0d7b954_appdaemon
    mode: single


<h2>Configuration</h2>

If you have the Solcast, Octopus and Solax integrations set up as specified above, there should be minimal configuration required. 

If you are running a different integration or inverter brand you will need to edit the `config.yaml` file in the appropriate section to select the correct `inverter_type`. 
You may also need to change the `device_name`. This is the name given to your inverter by your integration. The default is `solis` but this can also be changed in `config.yaml`.

E.g:

For the Core Modbus Integration:

    inverter_type: SOLIS_CORE_MODBUS
    device_name: solis

For the Solarman integration (legacy installs using https://github.com/StephanJoubert/home_assistant_solarman)

    inverter_type: SOLIS_SOLARMAN
    device_name: solis

For the Solarman integration (new installs using https://github.com/davidrapan/ha-solarman)

    inverter_type: SOLIS_SOLARMAN_V2
    device_name: solis
    

The `config.yaml` file also includes all the other configuration used by PV Opt. If you are using the default setup you shouldn't need to change this but you can edit anything by un-commenting the relevant line in the file. The configuration is grouped by inverter/integration and should be self-explanatory. Once PV Opt is installed the config is stored within entities in Home Assistant. It you want these over-ritten please ensure that `overwrite_ha_on_restart` is set to `true`:

    overwrite_ha_on_restart: true

<b><i>PV_Opt</b></i> needs to know the size of your battery and the power of your inverter: both when inverting battery to AC power and when chargingh tha battery. It will attempt to work these out from the data it has loaded (WIP) but you should check the following enitities in Home Assistant:

<h3>System Parameters</h3>

| Parameter | Units | Entity | Default Value |
| :-- | :--: | :--| :--:|
| Battery Capacity| Wh| `number.pvopt_batter_capacity_wh` | 10000|
| Inverter Power | W | `number.pvopt_inverter_power_watts` | 3600 |
| Charger Power | W | `number.pvopt_charger_power_watts` | 3500 |
| Inverter Efficiency | % | `number.pvopt_inverter_efficiency` | 97% |
| Charger Efficiency | % | `number.pvopt_charger_efficiency` | 91% |

There are then only a few things to control the optimisation process.  These have been grouped as follows:

<h3>Control Parameters</h3>
These are the main parameters that will control how PV Opt runs:

| Parameter | Units | Entity | Default | Description |
|:--|:--:| :-- | :--:|:--|
| Read Only Mode | `on`/`off` | `switch.pvopt_read_only` | On | Controls whether the app will actually control the inverter. Start with this on until you are happy the charge/discharge plan makes sense.
| Optimise Charging | `on`/`off` | `switch.pvopt_forced_charge` | On | Controls whether the app will calculate an Optimised plan. If `off` only the Base forecast will be updated.
| Optimise Discharging | `on`/`off` | `switch.pvopt_forced_discharge` | On | Controls whether the app will allow for forced discharge as well as charge
| Allow Cyclic | `on`/`off` | `switch.pvopt_allow_cyclic` | On | Controls whether the app will allow cycles of alternating charge/discharge |
| Use Solar |  `on`/`off` | `switch.pvopt_use_solar` | On | Controls whether the app will use the Solcast solar forecast. If set to Off no solar will be used but battery charging can still be optimised for a time-of use tariff. 
| Solcast Confidence Level | `number`| `number.pvopt_solcast_confidence_level` | Solcast | Selects which the Confidence Level for the Solcast forecast. Levels between 10% and 50% are weighted from the Solcast 10% and 50% forecasts. Levels between 50% and 90% are weighted from the Solcast 50% and 10% forecasts.|
| Optimser Frequency | minutes | `number.pvopt_optimise_frequency_minutes` | 10 | Frequency of Optimiser calculation |

<h3>Consumption Parameters</h3>
These parameters will define how PV Opt estimates daily consumption:

| Parameter | Units | Entity | Default | Description |
|:--|:--:| :-- | :--:|:--|
| Use Consumption History|`on`/`off` | `switch.pvopt_use_consumption_history` | On | Toggles whether to use actual <b>consumption history</b> or an estimated <b>daily consumption</b>
| <b>Consumption History Parameters
| Load History Days | days | `number.pvopt_consumption_history_days` | 7 | Number of days of consumption history to use when predicting future load |
| Load Margin | % | `number.pvopt_consumption_margin` | 10% | Margin to add to historic load for forecast (safety factor) |
| Weekday Weighting| fraction | `number.pvopt_day_of_week_weighting` | 0.5 | Defines how much weighting to give to the day of the week when averaging the load. 0.0 will use the simple average of the last `n` days based on `load_history_days` and 1.0 will just used the same day of the week within that window. Values inbetween will weight the estimate accordingly. If every day is the same use a low number. If your usage varies daily use a high number.
| <b>Daily Consumption Parameters
| Daily Consumption | kWh | `number.pvopt_daily_consumption_kwh` | 17 | Estimated daily consumption to use when predicting future load |
| Shape Consumption Profile | `on`/`off` | `switch.pvopt_shape_consumption_profile` | On | Defines whether to shapoe the consumption to a typical daily profile (`on`) or to assume constant usage (`off`). The shape of the daily profile can be modified within config.yaml. |

<h3>EV parameters</h3>

| Parameter | Units | Entity | Default | Description |
|:--|:--:| :-- | :--:|:--|
| EV Charger| None / Zappi / Other | `select.pvopt_ev_charger` | None | Set EV Charger Type. At the current release, only 'Zappi' is supported, 'Other' is unused and is for a future release. Note: Zappi support requires the MyEnergi integration to be installed. |
| EV Part of House Load| On / Off | `switch.pvopt_ev_part_of_house_load` | On | Prevents house battery discharge when EV is charging. If your EV Charger is wired so it is seen as part of the house load, then it will discharge to the EV when the EV is charging. Setting this to On prevents this, as well as ensuring that any EV consumption is removed from Consumption History. If your Zappi is wired on its own Henley block and thus outside of what the inverter CT clamp will measure, then set this to Off. Note: PV Opt does not support allowing the house battery to be used to charge the car. |
| Car Charge Plan| kWh | `switch.control_car_charging` | Off | Toggle Car Plan generation On/Off. For users on Agile, setitng to On will generate candidate car charging plan on each optimiser run based on the settings below. The candidate plan is made active upon car plugin, or via Dashbaord command (see "Transfer Car Charge Plan" below). The active car charging plan is output live on binary_sensor.pvopt_car_charging_slot for use in HA automations to switch the EV charger on and off. An example HA automation to control a Zappi charger is included at XXXXXXX. Intelligent Octopus Go users should set this to Off. If Off, the rest of the EV parameters below have no effect. |
| Transfer Car Charge Plan| On/Off | `switch.transfer_car_charge_plan` | 30 | Make Candidate Car Charging Plan the active plan. Useful if adjusting any of the below paramaters after the car has been plugged in. This will automatically be set back to Off after the plan is transferred. This ensures any external HA automations used to auto-calculate "Car Charge to Add" based on car SOC don't corrupt the car charging plan once the car starts charging. |
| EV Charger Power| W | `number.pvopt_ev_charger_power_watts` | 7000 | Set EV charger power. |
| EV Batttery Capacity| kWh | `number.pvopt_ev_battery_capacity_kwh` | 60 | Set EV Battery Capacity.   |
| Car Ready By| Time | `select.car_charging_ready_by` | 06:30 | Set Time for when the Car is to be ready by.   |
| Car Charge to Add| % | `number.ev_charge_target_percent` | 30 | % of 'charge to add' to the car. I.e if your car is at 40% and want it to be charged to 90% then set this to 50%.  |
| Car Charge Slot max price| p | `number.max_ev_price_p` | 30 | Maximum 1/2 hour slot price per kWh in pence added to the candidate car charging plan. Disable by setting to 0. Note: setting a low value may mean the car will not charge to the required SOC if overnight Agile rates are high. |
| Car Charge Efficiency| % | `number.ev_charger_efficiency_percent` | 92 | Charging Efficiency for EV Charger/Car. 92% is average for most cars/chargers but adjust if the car is consistently undercharging or overcharging against its target. |
| Prevent Discharge| On/off | `switch.pvopt_prevent_discharge` | Off | Set to prevent house battery discharge. Clear to allow normal inverter use. Useful for house battery dicharge prevention when high loads are being used (EVs not otherwise coupled in to Pv_opt, showers etc). When set, does not affect the house battery charge plan. |
| id_zappi_plug_status| `string` |    | Autodetected | In config.yaml, remap the autodeteted Zappi car plugin status entity to a named entity. If you have a single Zappi then this line should remain commented out. If you have multiple zappis then if required, change the entity name to the Zappi linked to IOG / load the Agile car charging plan. |

<h3>Pricing Parameters</h3>
These parameters set the price that PV Opt uses:

<h4>Octopus Tariffs (usinng the Octopus API)</h4>

| Parameter | Units | Entity | Default | Description |
|:--|:--:| :-- | :--:|:--|
| Octopus Auto|`on`/`off` | `octopus_auto` | On | Read tariffs from the Octopus Energy integration. If successful this over-rides the following parameters
| Octopus Account | `string`  | `octopus_account` |  | Octopus Account ID (Axxxxxxxx) - not required if Octopus Auto is set|
| Octopus API Key | `string` | `octopus_api_key` |  | Octopus API Key - not required if Octopus Auto is set |
| Octopus Import Tariff Code| fraction | `octopus_import_tariff_code` |  | Import Tariff Code (eg `E-1R-AGILE-23-12-06-G`) |
| Octopus Export Tariff Code| fraction | `octopus_export_tariff_code` |  | Export Tariff Code (eg `E-1R-AGILE-OUTGOING-19-05-13-G`)| 

<h4>Manual Tariffs</h4>

Import and/or export tarifs can be set manually as follows. These can be combined with Octopus Account Codes (ie you could set Octopus Agile for input using `octopus_import_tariff_code` and a manual export). Manual tariffs <b>will not work</b> with either `Octopus Auto` or `Octopus Account`.

    manual_import_tariff: True
    manual_import_tariff_name: Test Importe
    manual_import_tariff_tz: GB
    manual_import_tariff_standing: 43
    manual_import_tariff_unit:
      - period_start: "00:00"
        price: 4.2
      - period_start: "05:00"
        price: 9.7
      - period_start: "16:00"
        price: 77.0
      - period_start: "19:00"
        price: -2.0

    manual_export_tariff: True
    manual_export_tariff_name: Test Export
    manual_export_tariff_tz: GB
    manual_export_tariff_unit:
      - period_start: "01:00"
        price: 14.2
      - period_start: "03:00"
        price: 19.7
      - period_start: "16:00"
        price: 50.0
      - period_start: "14:00"
        price: 0.0


<h3>Tuning Parameters</h3>
These parameters will tweak how PV Opt runs:

| Parameter | Units | Entity | Default | Description |
|:--|:--:| :-- | :--:|:--|
| Pass threshold | % | `number.pvopt_pass_throshold_p` | 4p | The incremental cost saving that each iteration of the optimiser needs to show to be included. Reducing the threshold may marginally reduce the predicted cost but have more marginal charge windows. |
| Discharge threshold | % | `number.pvopt_discharge_throshold_p` | 5p | The incremental cost saving that each iteration of the discharge optimiser needs to show to be included. Reducing the threshold may marginally reduce the predicted cost but have more marginal discharge windows. |
| Slot threshold | % | `number.pvopt_slop_throshold_p` | 1p | The incremental cost saving that each 30 minute slot of the optimiser needs to show to be included. Reducing the threshold may marginally reduce the predicted cost but have more marginal charge/discharge windows. |
| Power Resolution | W | `number.pvopt_forced_power_group_tolerance` | 100 | The resolution at which forced charging / discharging is reported. Changing this will change the reporting of the charge plan but not the actual detail of it. |

<h3>Alternative Tariffs</h3>
PV Opt can also check what each day would have cost using any combination of Octopus tariffs. Run over time this can give you an idea of whether it would be worth switching. To  enable this simply add a block like this to `config.yaml`:

    id_daily_solar: sensor.{device_name}_power_generation_today
    alt_tariffs:
      - name: Agile_Fix
        octopus_import_tariff_code: E-1R-AGILE-23-12-06-G
        octopus_export_tariff_code: E-1R-OUTGOING-FIX-12M-19-05-13-G

      - name: Eco7_Fix
        octopus_import_tariff_code: E-2R-VAR-22-11-01-G
        octopus_export_tariff_code: E-1R-OUTGOING-FIX-12M-19-05-13-G

      - name: Flux
        octopus_import_tariff_code: E-1R-FLUX-IMPORT-23-02-14-G
        octopus_export_tariff_code: E-1R-FLUX-EXPORT-23-02-14-G

In this example three alternatives are tested. For each tariff pair the Base and Optimised net cost for yesterday are calculated and saved to an entity called `sensor.pvopt_opt_cost_name`. The state of this entity is the optimised cost and the base cost is saved as the `net_base` attribute.

<h2>Output</h2>

The app always produces a Base forecast of future battery SOC and the associated grid flow based on the forecast solar performance, the expected consumption and prices with no forced charging or discharging from the grid.. The total cost for today and tomorrow is written to `sensor.pvopt_base_cost` and the associated SOC vs time is written to the attributes of this entity allowing it to be graphes using `apex-charts`.

If `Optimise Charging` is enabled, an optimsised charging plan is calculated and writtemt to `sensor.pvopt_opt_cost`. This will also include a list of forced charge and discharge windows.

The easiest way to control and visualise this is through the `dashboards/pvopt_dashboard.yaml` Lovelace yaml file included in this repo.  If you're using the Solis Cloud integration, you can start with the `dashboards/pvopt_dashboard_solis_cloud.yaml`. Note that you will need to manually paste this into a dashboard and edit the charts to use the correct Octopus Energy sensors:

![Alt text](image-1.png)

This dashboards uses a couple of template sensors and time which will need adding to `/homeassistant/configuration.yaml`:

```
template:
  - sensor:
    - name: "Solis Grid Export Power"
      unique_id: solis_grid_export_power
      unit_of_measurement: W
      device_class: power
      state_class: measurement
      state: >-
        {{max(states('sensor.solis_meter_active_power') | float(0),0)}}    

    - name: "Solis Grid Import Power"
      unique_id: solis_grid_import_power
      unit_of_measurement: W
      device_class: power
      state_class: measurement
      state: >-
        {{max(-(states('sensor.solis_meter_active_power') | float(0)),0)}}

sensor:
  - platform: time_date
    display_options:
      - 'time'
      - 'date'
      - 'date_time'
      - 'date_time_utc'
      - 'date_time_iso'    
```
The dashboards also depend on the following Frontend components from HACS:
 - template-entity-row
 - bar-card
 - card-mod
 - Stack In Card
 - layout-card
 - apexcharts-card


<h2> Known Issues</h2>

<h3>Docker MariaDB Cache Size</h3>

If you are using MariaDB for your database in a standalone container (ie Docker or Proxmox) rather than the Home Assistnt Add-On you may find that AppDaemon struggles to pull in enough history with the default cache settings.

MariaDB defaults to an in memory cache of 10MB. increasing `innodb_buffer_pool_size` to will allow more history to be transferred. This setting does not appear to be available in the Add-On configuration.

Full details are here: https://github.com/fboundy/pv_opt/issues/270

<h2>Development - Adding Additional Inverters: the PV Opt API</h2>

PV Opt is designed to be <i>pluggable</i>. A simple API is used to control inverters. This is defined as follows:

<h3>Inverter Type</h3>

Each inverter type is defined by a string in the config.yaml file. This should be of the format: `BRAND_INTEGRATION` for example `SOLIS_SOLAX_MODBUS`. 

<h3>Inverter Module</h3>

PV Opt expects one module per inverter brand named `brand.py` which includes drives for all integrations/models associated with that brand. For example `solis.py` includes the drivers for `SOLIS_SOLAX_MODBUS`, `SOLIS_CORE_MODBUS` and `SOLIS_SOLARMAN`

Each module exposes the following:

<h4>Classes</h4>

The module exposes a single class `InverterController(inverter_type, host)`. The two required initialisation parameters are:

| Parameter | Type | Description |
| :--| :--: | :--|
|`inverter_type`| `str` | The `inverter_type` string from the `config.yaml` file
|`host` | `PVOpt` | The instance of `PV Opt` that has instantiated the inverter class. This allows the class to, for instance, write to the main log file simply be setting `self.log=host.log` and then calling `self.log()`

<h4>Class Attributes</h4>

The `InverterController` class must expose the following:

| Attribute | Key | Type | Description | Example from `SOLIS_SOLAX_MODBUS`|
|:--| :--:|:--:|:--|:--|
|`.config`| | `dict`| This dict contains all the names of all the entities that PV Opt requires to run plus a few other parameters that are common to all inverters. Some entries must be an `entity_id`: keys for these itesms start with `id_`. Others may be `enitity_id`s or numbers. `entity_id`s should ideally include `{device_name}` to allow for the subsititution of a defined device name where appropriate. |
||`maximum_dod_percent` | `str` / `int`| Maximum depth of discharge - nay be an entity_id or a number | `number.{device_name}_battery_minimum_soc`|
||`update_cycle_seconds` |`int`| Time in seconds between HA updates | 15|
||`supports_hold_soc` |`bool`| Flags whether the integration supports holding a fixed SOC | `true`|
||`id_battery_soc` | `str`|`entity_id` of Battery State of Charge | `number.{device_name}_battery_soc`|
||`id_consumption_today`| `str`|`entity_id` of Daily Consumption Total  | `sensor.{device_name}_house_load_today`|
||`id_grid_import_today`| `str`|`entity_id` of Daily Grid Import Total  | `sensor.{device_name}_grid_import_today`|
||`id_grid_export_today`| `str`|`entity_id` of Daily Grid Export Total  | `sensor.{device_name}_grid_export_today`|
|`.brand_config`| | `dict`| This dict contains all the names of all the entities that this brand/integration requires. These are only exposed for logging purposes and to allow the plug-in to use methods from the main app that use query `entity_id`s such as `.get_config(entity_id)` . A limited number of examples are given as this will vary for each plug-in.|
||`battery_voltage` | `str` / `int`| Battery voltage for converting power to current - nay be an entity_id or a number | `sensor.{device_name}_battery_voltage`|
||`id_timed_charge_start_hours` | `str`|`entity_id` of Timed Charge Start Hours | `number.{device_name}_timed_charge_start_hours`|
||`id_timed_charge_start_minutes` | `str`|`entity_id` of Timed Charge Start Minutes | `number.{device_name}_timed_charge_start_minutes`|
||`id_timed_charge_end_hours` | `str`|`entity_id` of Timed Charge End Hours | `number.{device_name}_timed_charge_end_hours`|
||`id_timed_charge_end_minutes` | `str`|`entity_id` of Timed Charge End Minutes | `number.{device_name}_timed_charge_end_minutes`|
||`id_timed_charge_current` | `str`|`entity_id` of Timed Charge Current | `number.{device_name}_timed_charge_current`|
|`.status`| |`dict`| This dict reports the current status of the inverter ||
||`charge`|`dict`| Dict of the Timed Charge Status with the following keys: `active: bool, start: datetime, end: datetime, power: float`|
||`discharge`|`dict`| Dict of the Timed Discharge Status with the following keys: `active: bool, start: datetime, end: datetime, power: float`|
||`hold_soc`|`dict`| Dict of the Hold_SOC Status with the following keys: `active: bool, soc: int`|


<h4>Methods</h4>

The `InverterController` class must expose the following:

|Method | Parameters | Returns | Description |
|:--| :-- | :--: | :--|
|`.enable_timed_mode()` | - | `None` | Switches the inverter mode to support timed changing and discharging |
|`.control_charge()` | `enable: bool` | `None` | Enable or disable timed charging |
| | `start: datetime, optional` |  | Start time of timed slot (default = don't set start) |
| | `end: datetime, optional` |  | End time of timed slot (default = don't set end) |
| | `power: float, optional` |  | Maximum power of timed slot (default = don't set power) |
|`.control_discharge()` | `enable: bool` | `None` | Enable or disable timed discharging |
| | `start: datetime, optional` |  | Start time of timed slot (default = don't set start) |
| | `end: datetime, optional` |  | End time of timed slot (default = don't set end) |
| | `power: float, optional` |  | Maximum power of timed slot (default = don't set power) |
|`.hold_soc()` | `soc` | `None` | Switch inverter mode to hold specified SOC (if supported) |


<h4>PV Opt Methods Available to the Inverter</h4>

The following methods may be useful for the inverter to call. If `self.host` is initialised to `host` they can be called using `self.host.method()`. As PV Opt is a sub-class of `hass.HASS` it includes all the AppDAemon methods listed here: https://appdaemon.readthedocs.io/en/latest/AD_API_REFERENCE.html 

|Method | Parameters | Returns / Decsription | 
|:--| :-- | :-- |
| `self.host.log`| `string`| Write `string` to the log file.
||`level: str, optional`| Optionally set the error level (default = `INFO`) |
| `self.host.get_state()`| `entity_id` | Home Assitant state of the entity |
|| `attributes: str, optional`| If attributes is set the attribute rather than the state is returned. If attribute is set to all a `dict` of all attributes is returned.
| `self.host.set_state()`| `state` | Set the Home Assitant state of the entity and optionally the attributes. Returns a `dict` of the new state|
||`entity_id: str`|
|| `attributes: dict, optional`|
| `self.host.entity_exists()` | `entity_id: str` | `bool` that confirms whether an entity exists in Home Assistant |
| `self.host.call_service()` | `service: str` | Call `service` in Home Assistant|
||`data: dict, optional`| Data to be supplied to the service e.g. for writing to the Solis Modbus registers: `data={"hub": "solis", "slave": 1, "address": 43011, "value": 15}`
