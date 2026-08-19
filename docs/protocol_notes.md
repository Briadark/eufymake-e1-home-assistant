# eufyMake E1 Protocol Notes

These notes are based on local project discovery and live E1 verification. Do
not paste real tokens, serial numbers, DSK keys, licenses, MAC addresses, or
user details into this file.

## Current Findings

- E1 devices appear as station model `V8260`.
- Station model `V8111` has been observed in the account cache but is an
  AnkerMake M5 3D printer and is intentionally out of scope for this project.
- Normal app communication is cloud-backed and MQTT/P2P-aware.
- EU accounts cache `make-app-eu.ankermake.com` and
  `aiot-api-eu.ankermake.com`.
- MQTT online state is cached separately from P2P online state.
- DSK/P2P material is cached by device serial number.
- The app cache contains consumable/service part data, including remaining
  percentages and remaining work life.
- The printer appears to expose no normal local TCP control port beyond AP/DNS
  service; local control likely requires the UDP/PPCS path rather than a simple
  HTTP or raw TCP LAN API.

## API Hosts

- `make-app.ankermake.com`
- `make-app-eu.ankermake.com`
- `make-app-us-qa.eufylife.com`
- `aiot-api-us.ankermake.com`
- `aiot-api-eu.ankermake.com`
- `aiot-api-qa.mkitreal.com`
- `aiot-api-eu-qa.mkitreal.com`

## MQTT Brokers

- `make-mqtt.ankermake.com`
- `make-mqtt-eu.ankermake.com`
- `make-mqtt-us-qa.eufylife.com`
- `make-mqtt-us-ci.eufylife.com`

## MQTT Auth And Transport

- Port is `8789` over MQTT/TLS.
- Username format is `eufy_<user_id>`.
- Password is the URL-decoded cached email address.
- Client id follows the desktop-app pattern
  `pc_<platform>_AnkerMakeStudio_direct_<user_id>_<random>_<timestamp_ms>`.
- Topic subscriptions must be exact; wildcard subscriptions are expected to be
  rejected by broker ACLs.
- Keepalive observed from the Windows app is very short, around one second.

## API Paths Seen In App

- `/v3/app/query_fdm_list`
- `/v3/app/equipment/get_dsk_keys`
- `/v3/app/query_makerpart_list`
- `/v3/app/query_maker_part`
- `/v3/app/overall/get_params`
- `/v3/passport/profile`
- `/v3/pc/passport/get_user_params`
- `/v3/pc/overall/get_config`

## MQTT Topics Seen In App

- `/phone/maker/<station_sn>/notice`
- `/phone/maker/<station_sn>/command/reply`
- `/phone/maker/<station_sn>/query/reply`
- `/phone/maker/<station_sn>/change_notice`
- `/phone/user/<user_id>/change_notice`
- `/device/maker/<station_sn>/command`
- `/device/maker/<station_sn>/query`

## MQTT Frame Format

- Two MQTT wire variants were investigated during discovery. The integration
  should keep accepting both response shapes until more app/account versions
  are tested.
- Variant A: AES-256-CBC encrypted JSON in an `MA` binary frame. The AES key is
  the E1 `secret_key` from `device_list.json`, decoded from hex. IV is the
  fixed ASCII value `3DPrintAnkerMake`. Frames use a little-endian total size,
  metadata bytes, ciphertext, and a one-byte XOR checksum.
- Variant A printer-to-app frames use a 24-byte header (`M5 = 0x06`).
- Variant A app-to-printer frames use a 64-byte header (`M5 = 0x02`) with a
  random desktop client GUID field.
- Variant B: AES-256-GCM encrypted JSON as a 4-byte big-endian length, 16-byte
  tag, and ciphertext. Reported nonce is the fixed ASCII value `3DPrintAnker`.
- Live test on this project account confirmed the E1 accepts Variant A/CBC
  frames on the EU broker and returns decodable Variant A/CBC replies.
- `commandType: 1027` with `value: 0` asks the E1 to publish a fresh status
  batch.
- `commandType: 1100` contains ink and waste tank status. Ink levels are stored
  as hundredths of a percent.
- `commandType: 1100` may arrive as one object or inside a batched list of
  status objects.
- Live payloads used `manufactureTime` for cartridge manufacture timestamps.

## Command Types Of Interest

- `1000`: printer state.
- `1027`: device query / fresh status request.
- `1068`: print job history with per-job ink consumption.
- `1100`: ink levels and waste tank telemetry.
- `1128`: MQTT/P2P status heartbeat/config.
- `1144`: command timeout configuration.
- `1171`: simple value report observed after device query.
- `1104`: pre-print checks.
- `1105`: snapshot/photo progress and height data.
- `1118`: multi-status response.
- `1154`: maintenance counter.
- `1156`: AP/WiFi status.

## Commands Seen In App

- `command_get_print_status`
- `command_get_device_info`
- `command_get_device_key`
- `command_get_current_device_sn`
- `command_get_net_status`
- `command_print`
- `command_print_pause`
- `command_print_resume`
- `command_print_stop`
- `command_take_photo`
- `command_zero_calibration`
- `command_zero_calibration_status`
- `command_open_change_white_ink`

## Next Questions

1. Which HTTP headers/signature fields are required for `/v3/app/query_fdm_list`?
2. Can a cached `auth_token` call the API directly from Python?
3. Which login endpoint/body is required to replace setup-export based
   configuration with region, email, password, and E1 selection?
4. Can LAN/AP mode expose enough status for a local-only Home Assistant mode?
5. Do other regions/accounts use the same MQTT CBC frame variant and broker
   certificate?
