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

    class SelectSelector:
        def __init__(self, config):
            self.config = config

    class TextSelectorConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class SelectSelectorConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class SelectSelectorMode:
        DROPDOWN = "dropdown"

    class TextSelectorType:
        EMAIL = "email"
        PASSWORD = "password"

    def all_validator(*args):
        return args

    config_entries.ConfigFlow = ConfigFlow
    config_entries.SOURCE_REAUTH = "reauth"
    config_entries.SOURCE_RECONFIGURE = "reconfigure"
    const.CONF_COUNTRY = "country"
    const.CONF_DEVICE_SN = "device_sn"
    const.CONF_EMAIL = "email"
    const.CONF_PASSWORD = "password"
    const.CONF_REGION = "region"
    const.DOMAIN = "eufymake_e1"
    const.REGION_EU = "eu"
    const.REGION_OPTIONS = ["us", "eu"]
    homeassistant.config_entries = config_entries
    homeassistant.helpers = helpers
    helpers.selector = selector
    selector.TextSelector = TextSelector
    selector.TextSelectorConfig = TextSelectorConfig
    selector.TextSelectorType = TextSelectorType
    selector.SelectSelector = SelectSelector
    selector.SelectSelectorConfig = SelectSelectorConfig
    selector.SelectSelectorMode = SelectSelectorMode
    voluptuous.All = all_validator
    voluptuous.In = In
    voluptuous.Length = Length
    voluptuous.Required = Required
    voluptuous.Schema = Schema
    sys.modules["custom_components"] = custom_components
    sys.modules["custom_components.eufymake_e1"] = package
    sys.modules["custom_components.eufymake_e1.const"] = const
    sys.modules["custom_components.eufymake_e1.countries"] = _load_module(
        "custom_components.eufymake_e1.countries",
        CONFIG_FLOW.parent / "countries.py",
    )
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


def test_country_options_include_default_country() -> None:
    module = load_config_flow_module()

    countries = {
        option["value"]: option["label"]
        for option in module.COUNTRY_OPTIONS
    }

    assert countries["NL"] == "Netherlands"


def test_captcha_image_uri_converts_base64_png() -> None:
    module = load_config_flow_module()

    assert module._captcha_image_uri("iVBORw0KGgo=") == (
        "data:image/png;base64,iVBORw0KGgo="
    )


def test_captcha_image_uri_preserves_data_uri() -> None:
    module = load_config_flow_module()

    assert module._captcha_image_uri("data:image/png;base64,abc") == (
        "data:image/png;base64,abc"
    )


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
