# eufyMake E1 for Home Assistant

[![Open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Briadark&repository=eufymake-home-assistant&category=integration)

Custom Home Assistant integration for the **eufyMake E1 UV printer** and its linked **Purifier P1**.

The integration connects through eufyMake's cloud and MQTT services and exposes printer status, ink information, accessory state, device metadata, and Purifier P1 controls in Home Assistant.

## Features

### eufyMake E1

- Setup from the Home Assistant integrations UI
- eufyMake account login with country selection, email, password, and CAPTCHA support
- Availability and connectivity sensors
- Firmware information
- Current accessory detection
- Ink level monitoring
- Ink manufacture and expiration information
- Days-until-expiration sensors
- Waste ink monitoring
- Device information including model, serial number, firmware, and hardware revision when available
- Bundled MQTT certificate, so no certificate file from the Windows app is required

### Purifier P1

When a Purifier P1 is linked to the E1, it is exposed as a separate Home Assistant device connected through the E1.

Supported functionality includes:

- Purifier status
- Purifier mode control:
  - Standby
  - Silent
  - High
  - Full power
  - Auto
- Auto delay-off control:
  - Immediately
  - 1 minute
  - 3 minutes
  - 5 minutes
  - 10 minutes
- Model and serial number
- Firmware version
- Hardware revision when provided by eufyMake

## Compatibility

### Supported

- **eufyMake E1 UV Printer**
  - Station model: `V8260`
- **eufyMake Purifier P1**
  - Model: `T5216` / `TS5216`
  - Must be linked to an E1

### Not supported

- **AnkerMake M5 / eufyMake Studio 3D printer**
  - Station model: `V8111`

Support for additional eufyMake devices may be added in the future.

## Installation with HACS

1. Make sure [HACS](https://www.hacs.xyz/) is installed in Home Assistant.
2. Click the HACS button at the top of this page.
3. Add this repository as an **Integration**.
4. Download **eufyMake E1**.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & services -> Add integration**.
7. Search for **eufyMake E1**.

## Setup

Enter your eufyMake account details:

- Country
- Email
- Password

If eufyMake requests CAPTCHA verification, Home Assistant will display the CAPTCHA image and ask for the answer before continuing.

Your password is used only during authentication and is **not stored** in the Home Assistant config entry.

### Upgrading from an older version

Existing installations can upgrade normally through HACS.

An older installation may receive a Home Assistant **reauthentication** request after upgrading. This is expected when the existing config entry does not yet contain the newer cloud authentication information required for features such as Purifier P1 support.

## Devices and entities

The E1 is created as its own Home Assistant device.

If a Purifier P1 is detected, Home Assistant creates a separate Purifier P1 device and links it to the E1 using Home Assistant's device hierarchy.

Device information can include:

- Product/model number
- Serial number
- Firmware version
- Hardware revision, when provided by eufyMake

For example:

- E1 model: `E1 (V8260)`
- Purifier model: `Purifier P1 (T5216)`

## Dashboard example

The example below uses only built-in Home Assistant cards. Entity IDs may differ depending on your Home Assistant installation.

![Dashboard example](docs/dashboard-example.png)

```yaml
type: vertical-stack
cards:
  - type: entities
    title: eufyMake E1
    show_header_toggle: false
    entities:
      - entity: sensor.eufymake_e1_availability
        name: Availability
      - entity: sensor.eufymake_e1_print_status
        name: Print status
      - entity: sensor.eufymake_e1_firmware_version
        name: Firmware
      - entity: sensor.eufymake_e1_current_accessory
        name: Current accessory
      - entity: sensor.eufymake_e1_mqtt_online
        name: MQTT online
      - entity: sensor.eufymake_e1_p2p_online
        name: P2P online

  - type: grid
    title: Ink levels
    columns: 3
    square: false
    cards:
      - type: gauge
        entity: sensor.eufymake_e1_cyan_ink
        name: Cyan
        min: 0
        max: 100

      - type: gauge
        entity: sensor.eufymake_e1_magenta_ink
        name: Magenta
        min: 0
        max: 100

      - type: gauge
        entity: sensor.eufymake_e1_yellow_ink
        name: Yellow
        min: 0
        max: 100

      - type: gauge
        entity: sensor.eufymake_e1_black_ink
        name: Black
        min: 0
        max: 100

      - type: gauge
        entity: sensor.eufymake_e1_white_ink
        name: White
        min: 0
        max: 100

      - type: gauge
        entity: sensor.eufymake_e1_gloss_ink
        name: Gloss
        min: 0
        max: 100

  - type: gauge
    entity: sensor.eufymake_e1_waste_ink
    name: Waste ink
    min: 0
    max: 100

  - type: entities
    title: Ink expiration
    show_header_toggle: false
    entities:
      - entity: sensor.eufymake_e1_cyan_ink_expiration_date
        name: Cyan expiration
      - entity: sensor.eufymake_e1_cyan_ink_days_until_expiration
        name: Cyan days left
      - entity: sensor.eufymake_e1_magenta_ink_expiration_date
        name: Magenta expiration
      - entity: sensor.eufymake_e1_magenta_ink_days_until_expiration
        name: Magenta days left
      - entity: sensor.eufymake_e1_yellow_ink_expiration_date
        name: Yellow expiration
      - entity: sensor.eufymake_e1_yellow_ink_days_until_expiration
        name: Yellow days left
      - entity: sensor.eufymake_e1_black_ink_expiration_date
        name: Black expiration
      - entity: sensor.eufymake_e1_black_ink_days_until_expiration
        name: Black days left
      - entity: sensor.eufymake_e1_white_ink_expiration_date
        name: White expiration
      - entity: sensor.eufymake_e1_white_ink_days_until_expiration
        name: White days left
      - entity: sensor.eufymake_e1_gloss_ink_expiration_date
        name: Gloss expiration
      - entity: sensor.eufymake_e1_gloss_ink_days_until_expiration
        name: Gloss days left
      - entity: sensor.eufymake_e1_waste_ink_expiration_date
        name: Waste ink expiration
      - entity: sensor.eufymake_e1_waste_ink_days_until_expiration
        name: Waste ink days left
```

## How it works

The eufyMake E1 does not currently provide a documented public Home Assistant API.

This integration uses the same general cloud and MQTT communication paths used by eufyMake software to retrieve device state and send supported commands.

Because these interfaces are undocumented, eufyMake firmware or cloud changes may require updates to this integration.

## Privacy and security

- Your eufyMake password is not stored in the Home Assistant config entry.
- Authentication tokens and device credentials are stored by Home Assistant because they are required for continued communication with the device.
- Do not publish Home Assistant diagnostics, logs, packet captures, or cache exports without reviewing them first.

They may contain:

- Authentication tokens
- Serial numbers
- Device keys
- Account identifiers

## Issues and feedback

If you find a bug or have information about another eufyMake device, please open an issue:

https://github.com/Briadark/eufymake-home-assistant/issues

When reporting a problem, avoid posting credentials, authentication tokens, device keys, or other private account information.

## Disclaimer

This project is not affiliated with, endorsed by, or supported by eufyMake, AnkerMake, or Anker Innovations.

eufyMake and AnkerMake product names and trademarks belong to their respective owners.
