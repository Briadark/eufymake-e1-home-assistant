# eufyMake E1 Home Assistant Integration

Experimental Home Assistant custom integration for the eufyMake E1 UV printer.

The current first milestone is discovery and read-only status. The integration
uses the eufyMake cloud MQTT path for live E1 status:

- API hosts include `make-app*.ankermake.com` and `aiot-api*.mkitreal.com`.
- MQTT brokers include `make-mqtt.ankermake.com` and EU variants.
- E1 devices are station model `V8260`; `V8111` is an AnkerMake M5 3D printer
  and is intentionally out of scope.
- The app contains E1-oriented commands for status, ink state, print status,
  firmware, white ink cycle, zero calibration, snapshots, and file transfer.

Do not commit real device cache exports, tokens, DSK keys, serials, or licenses.

## Home Assistant UI Setup

This custom integration is built to appear in Settings -> Devices & services.
That requires `config_flow.py` and `"config_flow": true` in `manifest.json`.

For a manual test install, copy `custom_components/eufymake_e1` into your Home
Assistant config directory:

```text
<config>/custom_components/eufymake_e1
```

For local development on Windows, a junction is easier:

```powershell
New-Item -ItemType Junction `
  -Path "C:\path\to\homeassistant\config\custom_components\eufymake_e1" `
  -Target "C:\VSCode\eufymake-e1-home-assistant\custom_components\eufymake_e1"
```

Restart Home Assistant, then add "eufyMake E1" from Devices & services.

The preferred setup path is now eufyMake account login. Select your account
region, enter your eufyMake email and password, then select the E1 if more than
one supported printer is found. The password is used only during setup and is not
stored in the Home Assistant config entry.

The setup export path remains available as a fallback. It uses a one-time JSON
export from the Windows machine where eufyMake Studio is already logged in. This
avoids manually typing the E1 serial number, user ID, MQTT host, and device
secret key into separate fields.

On the Windows machine, run:

```powershell
py .\tools\export_home_assistant_setup.py
```

Then paste the printed JSON into the Home Assistant setup form. Treat that JSON
as private because it contains the E1 MQTT credentials.

The MQTT broker uses a private AnkerMake/eufyMake certificate. The integration
bundles the required trust anchor so Home Assistant does not need access to the
Windows app certificate file.

## Protocol Notes

The integration shell is intentionally read-only until the protocol is proven.
The likely architecture is:

1. Python client library authenticates against eufyMake/AnkerMake cloud.
2. Client fetches device list and DSK/P2P material.
3. Client subscribes to MQTT topics for status and command replies.
4. Home Assistant coordinator exposes sensors and later safe services.

The config flow accepts a setup export for now. The target setup experience is
region plus eufyMake account login, followed by E1 device selection.

Known topic patterns from the Windows app:

- `/phone/maker/<station_sn>/notice`
- `/phone/maker/<station_sn>/command/reply`
- `/phone/maker/<station_sn>/query/reply`
- `/phone/maker/<station_sn>/change_notice`
- `/phone/user/<user_id>/change_notice`
- `/device/maker/<station_sn>/command`
- `/device/maker/<station_sn>/query`

MQTT payloads are encrypted E1 frames. The client currently uses the CBC `MA`
frame variant verified against an E1 on the EU broker. It also has an offline
parser for decrypted `commandType: 1100` ink and waste-tank status messages.

Known command names include `command_get_print_status`,
`command_get_device_info`, `command_get_device_key`, `command_print`,
`command_print_pause`, `command_print_resume`, `command_print_stop`,
`command_zero_calibration`, and `command_take_photo`.

## Cache Inspection

Use the summary helper for a safe high-level view of the local eufyMake Studio
cache:

```powershell
python .\tools\summarize_eufymake_cache.py
```

Use the lower-level helper to inspect cache structure without printing
secret-looking values:

```powershell
python .\tools\inspect_eufymake_cache.py
```

Prepare the cached inputs for a future MQTT probe without connecting to the
broker:

```powershell
python .\tools\prepare_mqtt_probe.py
```

Decode a saved MQTT payload capture offline:

```powershell
python .\tools\decode_mqtt_payload.py .\capture.bin
```

Experimental live MQTT status probe dependencies are intentionally separate from
the Home Assistant scaffold:

```powershell
python -m pip install -r .\requirements-discovery.txt
python .\tools\live_mqtt_status_probe.py
```

The default cache path is:

`%APPDATA%\eufyMake Studio Profile\cache\offline\device_info`

More project notes:

- [Protocol notes](docs/protocol_notes.md)
- [Development plan](docs/development_plan.md)
