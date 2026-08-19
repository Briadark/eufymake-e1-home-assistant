# eufyMake E1 for Home Assistant

[![Open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Briadark&repository=eufymake-e1-home-assistant&category=integration)

Custom Home Assistant integration for the eufyMake E1 UV printer.

This integration is experimental and read-only. It connects through the
eufyMake cloud MQTT path and exposes printer status as Home Assistant sensors.

## Features

- Setup from the Home Assistant integrations UI.
- eufyMake account login with country dropdown, email, password, and captcha
  support.
- Sensors for availability, firmware, connectivity, ink levels, ink expiration,
  and waste ink.
- Bundled MQTT certificate, so no certificate file from the Windows app is
  needed.

## Compatibility

Supported:

- eufyMake E1, station model `V8260`

Not supported:

- AnkerMake M5 / eufyMake Studio 3D printer, station model `V8111`

## Install With HACS

1. Make sure HACS is installed in Home Assistant.
2. Click the HACS button above.
3. Add this repository as an `Integration`.
4. Download `eufyMake E1`.
5. Restart Home Assistant.
6. Go to Settings -> Devices & services -> Add integration.
7. Search for `eufyMake E1`.

## Setup

Enter your eufyMake account details:

- Country
- Email
- Password

If eufyMake asks for captcha verification, Home Assistant shows the captcha
image and asks for the answer before continuing.

Your password is used only during setup and is not stored in the Home Assistant
config entry.

## Notes

This project is not affiliated with eufyMake, AnkerMake, or Anker.

Do not share Home Assistant diagnostics, logs, or local cache exports publicly
unless you have checked that they do not contain tokens, serial numbers, or
device keys.
