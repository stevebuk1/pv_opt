# %%
import hashlib
import hmac
import base64
import json
import re
import requests
from http import HTTPStatus
from datetime import datetime, timezone
import pandas as pd

# def getInverterList(config):
#     body = getBody(stationId=config['plantId'])
#     print(body)
#     body = '{"stationId":"'+config['plantId']+'"}'
#     print(body)
#     header = prepare_header(config, body, INVERTER_URL)
#     response = requests.post("https://www.soliscloud.com:13333"+INVERTER_URL, data = body, headers = header)
#     inverterList = response.json()
#     inverterId = ""
#     for record in inverterList['data']['page']['records']:
#       inverterId = record.get('id')
#     return inverterList['data']['page']['records'][0]
INVERTER_DEFS = {
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

    def __init__(self, username, password, key_id, key_secret, plant_id):
        self.username = username
        self.key_id = key_id
        self.key_secret = key_secret
        self.plant_id = plant_id
        self.md5passowrd = hashlib.md5(password.encode("utf-8")).hexdigest()
        self.token = ""

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
        authorization = "API " + self.key_id + ":" + sign.decode("utf-8")

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

    @property
    def is_online(self):
        return self.inverter_details["state"] == 1

    @property
    def last_seen(self):
        return pd.to_datetime(int(self.inverter_details["dataTimestamp"]), unit="ms")

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

    def read_code(self, cid):
        if self.token == "":
            self.login()

        if self.token != "":
            body = self.get_body(inverterSn=self.inverter_sn, cid=cid)
            headers = self.header(body, self.URLS["atRead"])
            headers["token"] = self.token
            response = requests.post(self.URLS["root"] + self.URLS["atRead"], data=body, headers=headers)
            if response.status_code == HTTPStatus.OK:
                return response.json()["data"]["msg"]

    def login(self):
        body = self.get_body(username=self.username, password=self.md5passowrd)
        header = self.header(body, self.URLS["login"])
        response = requests.post(self.URLS["root"] + self.URLS["login"], data=body, headers=header)
        status = response.status_code
        if status == HTTPStatus.OK:
            result = response.json()
            self.token = result["csrfToken"]
            print("Logged in to SolisCloud OK")

        else:
            print(status)

    def mode_switch(self):
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

    def set_timer(self, direction, start, end, power):
        voltage = 50
        current_times = self.timed_status()
        new_times = current_times.copy()
        new_times[direction]["start"] = start
        new_times[direction]["end"] = end
        new_times[direction]["current"] = power / voltage
        current_time_string = self.read_code(103)
        new_time_string = self.get_time_string(new_times)
        if new_time_string != current_time_string:
            return self.set_code("103", new_time_string)
        else:
            return {"code": -1}


# %%
if __name__ == "__main__":
    config = {
        "key_secret": "735f96b6131b4691af944de80d2f1a1f",
        "key_id": "1300386381676670076",
        "plant_id": "1298491919448891215",
        "username": "boundywindsor@gmail.com",
        "password": "7y@-Ekdh&@F9",
    }

    sc = SolisCloud(**config)
    sc.login()
    print(sc.mode_switch())
    print(sc.timed_status())

# %%
sc.set_timer("charge", pd.Timestamp("00:50"), pd.Timestamp("01:00"), 3000)
# %%
sc.set_mode_switch(35)
# %%
r=sc.set_code(696, 3600)
# %%

# %%
