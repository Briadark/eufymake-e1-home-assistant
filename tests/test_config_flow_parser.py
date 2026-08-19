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
    helpers = types.ModuleType("homeassistant.helpers")
    selector = types.ModuleType("homeassistant.helpers.selector")
    voluptuous = types.ModuleType("voluptuous")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            return super().__init_subclass__()

    class Required:
        def __init__(self, key, **kwargs):
            self.key = key
            self.kwargs = kwargs

    class Length:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class In:
        def __init__(self, container):
            self.container = container

    class Schema:
        def __init__(self, value):
            self.value = value

    class TextSelector:
        def __init__(self, config):
            self.config = config

    class TextSelectorConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class TextSelectorType:
        EMAIL = "email"
        PASSWORD = "password"

    def all_validator(*args):
        return args

    config_entries.ConfigFlow = ConfigFlow
    const.CONF_COUNTRY = "country"
    const.CONF_DEVICE_SN = "device_sn"
    const.CONF_EMAIL = "email"
    const.CONF_PASSWORD = "password"
    const.CONF_REGION = "region"
    const.CONF_SETUP_EXPORT = "setup_export"
    const.DOMAIN = "eufymake_e1"
    const.REGION_EU = "eu"
    const.REGION_OPTIONS = ["us", "eu"]
    homeassistant.config_entries = config_entries
    homeassistant.helpers = helpers
    helpers.selector = selector
    selector.TextSelector = TextSelector
    selector.TextSelectorConfig = TextSelectorConfig
    selector.TextSelectorType = TextSelectorType
    voluptuous.All = all_validator
    voluptuous.In = In
    voluptuous.Length = Length
    voluptuous.Required = Required
    voluptuous.Schema = Schema
    sys.modules["custom_components"] = custom_components
    sys.modules["custom_components.eufymake_e1"] = package
    sys.modules["custom_components.eufymake_e1.const"] = const
    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.selector"] = selector
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


def test_device_label_includes_suffix_and_firmware() -> None:
    module = load_config_flow_module()

    label = module._device_label(
        {
            "station_sn": "AKTESTE100000001",
            "product_name": "eufyMake E1",
            "main_sw_version": "4.0.2",
        }
    )

    assert label == "eufyMake E1 0001 (4.0.2)"
