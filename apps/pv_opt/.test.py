# %%
from datetime import datetime, time

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pvpy as pvpy
import requests
import yaml
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

entities = [
    "pv_total_power",
    "battery_input_energy",
    "battery_output_energy",
    "grid_import_power",
    "grid_export_power",
    "bypass_load",
    "house_load",
]

token = "C1JXqu3wKSKVzGKs3n3Hu7sx1SG2L0RV8cjzt6gLUogh6DAfoik-aOMGJD8L1ZJm1Pj0JDWhTNw8brRem5aXpw=="
org = "ToppinHouse"
url = "http://192.168.4.181:8086"
bucket = "ToppinHouse"

write_client = InfluxDBClient(url=url, token=token, org=org)
# Initialize the InfluxDB client
client = InfluxDBClient(url=url, token=token, org=org)
query_api = client.query_api()

series = []
for entity in entities:
    query = f'from(bucket: "{bucket}") |> range(start: -36h) |> filter(fn: (r) => r.entity_id == "solis_{entity}")'

    # Execute the query
    result = query_api.query(org=org, query=query)

    # Process the results
    data = [{"Time": record.get_time(), "Value": record.get_value()} for record in result[-1].records]
    series += [pd.DataFrame(data)]
    series[-1] = series[-1].set_index("Time").resample("1min").mean().fillna(0)["Value"].rename(entity)
df = pd.concat(series, axis=1)
df = df.resample("5min").mean()
# Close the client
client.close()

# %%
