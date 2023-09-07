#!/usr/bin/env python3.8
#pylint: skip-file

# -----------------------------------------------------------------------------
# Proprietary License
# -----------------------------------------------------------------------------
#
# This script is proprietary software and is only licensed for use within
# the context of the specified project. Redistribution or use of this script
# outside the authorized project is strictly prohibited without explicit
# written permission from the author.
#
# -----------------------------------------------------------------------------
# Author: Rick Lan
# Year: 2023
# -----------------------------------------------------------------------------

from openpilot.common.realtime import Ratekeeper, set_core_affinity, set_realtime_priority
from openpilot.common.params import Params
from openpilot.common.basedir import PERSIST, BASEDIR
from datetime import datetime, timedelta
import jwt
import json
from openpilot.system.hardware import HARDWARE, PC, TICI
from cereal import car
import os
import base64
from urllib import request, parse, error
import cereal.messaging as messaging
import threading
import io

import subprocess
from typing import List, Optional

DP_HOST = "http://127.0.0.1:5000" if PC else "https://dragonpilot.org"
OTISSERV_API_VERSION = "v1"
DEVICE_URL = DP_HOST + '/api/' + OTISSERV_API_VERSION + '/devices'

DP_DEVICE_ID = "dp_nav_device_id"
MAPBOX_TOKEN_PARAM = "dp_nav_mapbox_token"

DP_PATCH_MARKER_BEGIN = '### dp_patch_begin ###'
DP_PATCH_MARKER_END = '### dp_patch_end ###'

DP_STOCK_BEGIN = '### dp_stock_begin ###'
DP_STOCK_END = '### dp_stock_end ###'

HEADERS = {
  'User-Agent': f"otisserv-{OTISSERV_API_VERSION}",
  'Content-Type': 'application/json',
}

DUMMY_FILES = ['../assets/navigation/direction_fork.png', '../assets/navigation/direction_flag.png', '../assets/navigation/direction_invalid.png']


_DEBUG = False


def _debug(msg):
  if _DEBUG:
    print(msg)

###################### get_origin begin ######################
def run_cmd(cmd: List[str]) -> str:
  return subprocess.check_output(cmd, encoding='utf8').strip()

def run_cmd_default(cmd: List[str], default: Optional[str] = None) -> Optional[str]:
  try:
    return run_cmd(cmd)
  except subprocess.CalledProcessError:
    return default

def get_origin(default: Optional[str] = None) -> Optional[str]:
  try:
    local_branch = run_cmd(["git", "name-rev", "--name-only", "HEAD"])
    tracking_remote = run_cmd(["git", "config", "branch." + local_branch + ".remote"])
    return run_cmd(["git", "config", "remote." + tracking_remote + ".url"])
  except subprocess.CalledProcessError:  # Not on a branch, fallback
    return run_cmd_default(["git", "config", "--get", "remote.origin.url"], default=default)
###################### get_origin end ######################

def patch_mapbox_token():
  import re
  import os

  script_path = os.path.join(BASEDIR, "launch_env.sh")

  mapbox_token = None
  if os.path.isfile("/data/media/0/" + MAPBOX_TOKEN_PARAM):
    with open("/data/media/0/" + MAPBOX_TOKEN_PARAM, 'r') as f:
      mapbox_token = f.read().strip()
  if not mapbox_token:
    return

  # Read the contents of the script
  with open(script_path, 'r') as file:
    script_contents = file.read()

  if DP_STOCK_BEGIN in script_contents and DP_STOCK_END in script_contents:
    return

  # Check if MAPBOX_TOKEN is already defined in the script
  if not re.search(r'\bMAPBOX_TOKEN\b', script_contents) and mapbox_token is not None:
    # Append the export statement to the script
    updated_contents = f'{script_contents}\n{DP_PATCH_MARKER_BEGIN}\nexport MAPBOX_TOKEN="{mapbox_token}"\n{DP_PATCH_MARKER_END}'

    # Write the updated contents back to the script
    with open(script_path, 'w') as file:
      file.write(updated_contents)

    _debug("[otisserv] MAPBOX_TOKEN patched.")


def unpatch_mapbox_token():
  import os

  script_path = os.path.join(BASEDIR, "launch_env.sh")

  # Read the contents of the script
  with open(script_path, 'r') as file:
    script_contents = file.read()

  # Check if the patch markers exist in the script contents
  if DP_PATCH_MARKER_BEGIN in script_contents and DP_PATCH_MARKER_END in script_contents:
    # Remove the patch and the content between the markers
    begin_index = script_contents.find(DP_PATCH_MARKER_BEGIN)
    end_index = script_contents.find(DP_PATCH_MARKER_END) + len(DP_PATCH_MARKER_END)
    updated_contents = script_contents[:begin_index] + script_contents[end_index:]

    # Write the updated contents back to the script
    with open(script_path, 'w') as file:
      file.write(updated_contents)

    _debug("[otisserv] MAPBOX_TOKEN unpatched.")


class OtisApi:
  def __init__(self):
    self._params = Params()
    self._serial = HARDWARE.get_serial()
    _debug(f"[otisserv] serial identified: {self._serial}")
    self._frame = 0

    self._allow_sync = False
    self._device_id = None
    self._device_name_sent = False
    self._username = None
    self._username_prev = None
    self._private_key = self._get_private_key()
    self._is_offroad = False
    self._is_offroad_prev = False
    self._sm = messaging.SubMaster(['gpsLocationExternal'])
    self._last_updated = None
    self._last_updated_prev = None
    self._last_event = None
    self._last_event_prev = None
    self._is_offline = False
    self._language = None
    self._language_prev = None

    # use threads for these process
    self._snapshot_thread = None
    self._destination_thread = None


  def update(self):
    self._set_variables()
    self._frame += 1

  def _set_variables(self):
    if self._frame % 3 != 0:
      self._allow_sync = False

    if not PC:
      if self._frame % 3 == 0:
        self._is_offroad = self._params.get_bool("IsOffroad")

    if self._frame % 3 == 0 and self._device_id is None:
      self._register()

    if self._frame % 3 == 0 and self._username is None:
      self._set_username()

    if self._frame % 3 == 0 and self._language is None:
      self._set_language()

    if self._frame % 3 == 0 and self._device_id is not None and self._username is not None:
      self._allow_sync = True

  def _get_mapbox_token(self):
    if os.path.isfile(f"/data/media/0/{MAPBOX_TOKEN_PARAM}"):
      with open(f"/data/media/0/{MAPBOX_TOKEN_PARAM}", 'r') as f:
        return f.read().strip()

  def _set_device_id(self):
    with open(f"{PERSIST}/{DP_DEVICE_ID}") as f:
      self._device_id = f.read()
    _debug(f"[otisserv] device_id identified: {self._device_id}")

  def _has_device_id(self):
    return os.path.isfile(f"{PERSIST}/{DP_DEVICE_ID}")

  def _set_language(self):
    self._language = self._params.get('LanguageSetting', encoding='utf8')
    self._language = self._language.replace('main_', '')
    if self._language == "zh-CHT":
      self._language = "zh-TW"
    elif self._language == "zh-CHS":
      self._language = "zh-CN"

  def _get_device_name(self):
    if PC:
      return "MOCK"
    try:
      cp = car.CarParams.from_bytes(self._params.get("CarParamsPersistent"))
      device_name = cp.carFingerprint
    except Exception:
      device_name = None

    return device_name

  def _get_public_key(self):
    if os.path.isfile(f"{PERSIST}/comma/id_rsa.pub"):
      with open(f"{PERSIST}/comma/id_rsa.pub") as f:
        return f.read()
    return ""

  def _get_private_key(self):
    if os.path.isfile(f"{PERSIST}/comma/id_rsa"):
      with open(f"{PERSIST}/comma/id_rsa") as f:
        return f.read()
    return None

  def _set_username(self):
    try:
      if PC:
        self._username = "efinilan"
        return
      self._username = self._params.get("GithubUsername", encoding='utf-8')
      if self._username == "openpilot":
        self._username = None
    except Exception:
      self._username = None

  def _write_device_id(self, device_id):
    if TICI:
      os.system(f"sudo su -c 'sudo mount -o rw,remount /persist'")
    os.system(f'printf "%s" {device_id} > {PERSIST}/{DP_DEVICE_ID}')
    if TICI:
      os.system(f"sudo su -c 'sudo mount -o ro,remount /persist'")

  def _get_register_token(self):
    return jwt.encode({'register': True, 'exp': datetime.utcnow() + timedelta(hours=1)}, self._private_key, algorithm='RS256')

  def _get_access_token(self, extra=None):
    payload = {
      'exp': datetime.utcnow() + timedelta(minutes=1),
    }
    if extra:
      payload["extra"] = extra

    token = jwt.encode(payload, self._private_key, algorithm='RS256')
    if isinstance(token, bytes):
      token = token.decode('utf8')

    return token

  def _device_get_onroad_position(self):
    self._sm.update(0)
    if self._sm.updated['gpsLocationExternal']:
      gps = self._sm['gpsLocationExternal']
      return gps.latitude, gps.longitude
    return None, None

  def _register(self):
    if self._has_device_id():
      self._set_device_id()
      return

    _debug(f"[otisserv] _register() begin")
    params = {
      "serial": self._serial,
      "public_key": self._get_public_key(),
      "dt": self._get_register_token(),
    }

    code, json_obj = self._send_request(params, method='POST')
    if code < 300 and 'id' in json_obj:
      self._write_device_id(json_obj.get('id'))
      self._set_device_id()

    elif code == 409:
      _debug(f"[otisserv] _register() end: {code}")

  def _process_snapshots_non_blocking(self):
    def _has_snapshot_request():
      code, json_obj = self._send_request(main_id=self._device_id, sub_route="snapshots")
      return code == 200

    def process_snapshot():
      if not _has_snapshot_request():
        return
      _debug(f"[otisserv] _process_snapshots_non_blocking() begin")
      if not PC:
        if TICI:
          from openpilot.system.camerad.snapshot.snapshot import jpeg_write, snapshot
        else:
          from openpilot.selfdrive.camerad.snapshot.snapshot import jpeg_write, snapshot
        ret = snapshot()

        files = []
        if ret is not None:
          def b64jpeg(x):
            if x is not None:
              f = io.BytesIO()
              jpeg_write(f, x)
              return base64.b64encode(f.getvalue()).decode("utf-8")
            else:
              return None
          if ret[0] is not None:
            files.append({'back': b64jpeg(ret[0])})
          if ret[1] is not None:
            files.append({'front': b64jpeg(ret[1])})
        else:
          raise Exception("not available while camerad is started")
      else:
        import random
        with open(random.choice(DUMMY_FILES), 'rb') as f:
          file = base64.b64encode(f.read()).decode('utf-8')
        files = [{'back': file}, {'front': file}]

      if files:
        data = json.dumps({"files": files}).encode('utf-8')
        self._send_request(main_id=self._device_id, sub_route="snapshots", timeout=180, method="POST", data=data)
      _debug(f"[otisserv] _process_snapshots_non_blocking() end")

    # Ignore if we have a query thread already running.
    if self._snapshot_thread is not None and self._snapshot_thread.is_alive():
      return

    self._snapshot_thread = threading.Thread(target=process_snapshot)
    self._snapshot_thread.start()

  def _send_request(self, params=None, main_id=None, sub_route=None, sub_route_id=None, data=None, method='GET', timeout=10):
    if params is None:
      params = {
        "dt": self._get_access_token(),
      }

    url = f"{DEVICE_URL}"
    if main_id is not None:
      url += f"/{main_id}"
      if sub_route is not None:
        url += f"/{sub_route}"
        url += f"/{sub_route_id}" if sub_route_id is not None else "/"
    else:
      url += "/"
    url += f"?{parse.urlencode(params)}"

    try:
      req = request.Request(url, data=data, headers=HEADERS, method=method)
      resp = request.urlopen(req, timeout=timeout)
      response = resp.read().decode('utf-8')
      json_object = json.loads('{}') if response == '' else json.loads(response)
      self._is_offline = False
      return resp.status, json_object
    except error.HTTPError as e:
      if e.code == 500:
        self._allow_sync = False
        self._is_offline = True
      # _debug(f"[otisserv] error.HTTPError: {e.code}: {e.reason}")
      return e.code, json.loads('{ "message": "error.HTTPError" }')
    except Exception as e:
      # OSError: [Errno 101] Network is unreachable
      # urllib.error.URLError: <urlopen error [Errno 101] Network is unreachable>
      # socket.gaierror: [Errno 7] No address associated with hostname
      self._allow_sync = False
      self._is_offline = True
      return 500, json.loads('{ "message": "Exception" }')

  def _get_status_params(self):
    token_payloads = {}

    # only update position when onroad
    # gpsLocationExternal is gone when offroad
    if not self._is_offroad:
      latitude, longitude = self._device_get_onroad_position()
      if latitude and longitude:
        token_payloads["latitude"] = latitude
        token_payloads["longitude"] = longitude

    # update offroad/onroad status
    token_payloads["is_offroad"] = self._is_offroad

    # only update username when there is a change
    if self._username != self._username_prev:
      token_payloads["username"] = self._username
    self._username_prev = self._username

    if self._language != self._language_prev:
      token_payloads["language"] = self._language
    self._language_prev = self._language

    # only update name + device_type + origin if it's not been sent once
    if not self._device_name_sent and (device_name := self._get_device_name()) is not None:
      token_payloads["name"] = device_name
      token_payloads["device_type"] = HARDWARE.get_device_type()
      token_payloads["origin"] = get_origin()
      self._device_name_sent = True

    params = {
      "dt": self._get_access_token(token_payloads),
    }
    return params

  def _process_updates(self, json_obj):
    if (val := json_obj.get("nav_mapbox_token")) != self._get_mapbox_token():
      if not PC:
        with open(f"/data/media/0/{MAPBOX_TOKEN_PARAM}", 'w') as file:
          file.write(val)
        unpatch_mapbox_token()
        if val:
          patch_mapbox_token()

  def _process_destination_non_blocking(self):
    def process_destination():
      _debug(f"[otisserv] _process_destination_non_blocking() begin")
      code, json_obj = self._send_request(main_id=self._device_id, sub_route="destinations")
      if code < 300 and len(json_obj):
        self._params.put("NavDestination", json.dumps(json_obj[0]))
      _debug(f"[otisserv] _process_destination_non_blocking() result: {code}")

    # Ignore if we have a query thread already running.
    if self._destination_thread is not None and self._destination_thread.is_alive():
      return

    self._destination_thread = threading.Thread(target=process_destination)
    self._destination_thread.start()

  def sync(self):
    if not self._allow_sync:
      return
    _debug(f"[otisserv] sync() begin")
    code, json_obj = self._send_request(self._get_status_params(), main_id=self._device_id, method='PATCH')
    if code < 300 and len(json_obj):
      if 'last_updated' in json_obj:
        self._last_updated = json_obj.get("last_updated")
      if 'last_event' in json_obj:
        self._last_event = json_obj.get("last_event")

    if self._last_updated_prev is None or self._last_updated != self._last_updated_prev:
      code, json_obj = self._send_request(main_id=self._device_id)
      if code < 300 and len(json_obj):
        self._process_updates(json_obj)
    self._last_updated_prev = self._last_updated

    if self._last_event_prev is None or self._last_event != self._last_event_prev:
      self._process_destination_non_blocking()
      self._process_snapshots_non_blocking()
    self._last_event_prev = self._last_event

    _debug(f"[otisserv] sync() end: {code}")

def otisserv_thread():
  set_core_affinity([1,])
  set_realtime_priority(1)
  otis = OtisApi()
  rk = Ratekeeper(1., print_delay_threshold=None)  # Keeps rate at 1Hz
  while True:
    otis.update()
    otis.sync()
    rk.keep_time()

def main():
  if TICI:
    patch_mapbox_token()
  otisserv_thread()


if __name__ == "__main__":
  main()
