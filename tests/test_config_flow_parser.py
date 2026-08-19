import importlib.util
import sys
import types
from pathlib import Path


CONFIG_FLOW = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "eufymake_e1"
    / "config_flow.py"
)


def load_config_flow_module():
    custom_components = types.ModuleType("custom_components")
    package = types.ModuleType("custom_components.eufymake_e1")
    const = types.ModuleType("custom_components.eufymake_e1.const")
    homeassistant = types.ModuleType("homeassistant")
    config_entries = types.ModuleType("homeassistant.config_entries")
    voluptuous = types.ModuleType("voluptuous")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            return super().__init_subclass__()

    class Required:
        def __init__(self, key):
            self.key = key

    class Length:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Schema:
        def __init__(self, value):
            self.value = value

    def all_validator(*args):
        return args

    config_entries.ConfigFlow = ConfigFlow
    const.CONF_DEVICE_SN = "device_sn"
    const.CONF_SETUP_EXPORT = "setup_export"
    const.DOMAIN = "eufymake_e1"
    homeassistant.config_entries = config_entries
    voluptuous.All = all_validator
    voluptuous.Length = Length
    voluptuous.Required = Required
    voluptuous.Schema = Schema
    sys.modules["custom_components"] = custom_components
    sys.modules["custom_components.eufymake_e1"] = package
    sys.modules["custom_components.eufymake_e1.const"] = const
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["voluptuous"] = voluptuous

    spec = importlib.util.spec_from_file_location(
        "custom_components.eufymake_e1.config_flow",
        CONFIG_FLOW,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_setup_export_inline() -> None:
    module = load_config_flow_module()

    parsed = module._parse_setup_export(
        """
        {
          "version": 1,
          "region": "eu",
          "device_sn": "AKTESTE100000001",
          "user_id": "fixture-user",
          "email": "fixture@example.com",
          "secret_key": "fixture-secret-key",
          "mqtt_host": "make-mqtt-eu.ankermake.com",
          "station_model": "V8260",
          "firmware_version": "4.0.2"
        }
        """
    )

    assert parsed["device_sn"] == "AKTESTE100000001"
    assert parsed["region"] == "eu"
    assert parsed["firmware_version"] == "4.0.2"


def test_parse_setup_export_rejects_m5() -> None:
    module = load_config_flow_module()

    try:
        module._parse_setup_export(
            """
            {
              "version": 1,
              "device_sn": "AKTESTM500000001",
              "user_id": "fixture-user",
              "email": "fixture@example.com",
              "secret_key": "fixture-secret-key",
              "mqtt_host": "make-mqtt-eu.ankermake.com",
              "station_model": "V8111"
            }
            """
        )
    except ValueError:
        return

    raise AssertionError("Expected M5 setup export to be rejected")
