import importlib.util
import sys
import types
from dataclasses import dataclass
from datetime import date
from pathlib import Path


COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "eufymake_e1"
)


def test_ink_sensors_are_grouped_by_channel() -> None:
    module = _load_sensor_module()

    keys = [description.key for description in module.SENSORS]

    assert keys[:9] == [
        "availability",
        "print_status",
        "firmware_version",
        "ink_c",
        "ink_c_expiration_date",
        "ink_c_days_until_expiration",
        "ink_c_expired",
        "ink_c_manufacture_date",
        "ink_c_status",
    ]
    assert keys[9:15] == [
        "ink_m",
        "ink_m_expiration_date",
        "ink_m_days_until_expiration",
        "ink_m_expired",
        "ink_m_manufacture_date",
        "ink_m_status",
    ]


def test_ink_expiration_sensor_returns_date_value() -> None:
    module = _load_sensor_module()
    data = {
        "ink_details": {
            "C": {
                "expiration_date": "2026-08-28",
                "manufacture_date": "2025-08-28",
                "days_until_expiration": 10,
                "expired": False,
                "status": 1,
            }
        }
    }

    descriptions = {description.key: description for description in module.SENSORS}

    assert descriptions["ink_c_expiration_date"].value_fn(data) == date(2026, 8, 28)
    assert descriptions["ink_c_manufacture_date"].value_fn(data) == date(2025, 8, 28)
    assert descriptions["ink_c_days_until_expiration"].value_fn(data) == 10
    assert descriptions["ink_c_expired"].value_fn(data) is False


def _load_sensor_module():
    _stub_homeassistant()
    package = types.ModuleType("custom_components.eufymake_e1")
    package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["custom_components.eufymake_e1"] = package
    sys.modules["custom_components.eufymake_e1.const"] = _load_module(
        "custom_components.eufymake_e1.const",
        COMPONENT_DIR / "const.py",
    )

    return _load_module(
        "custom_components.eufymake_e1.sensor",
        COMPONENT_DIR / "sensor.py",
    )


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _stub_homeassistant() -> None:
    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    sensor = types.ModuleType("homeassistant.components.sensor")
    config_entries = types.ModuleType("homeassistant.config_entries")
    const = types.ModuleType("homeassistant.const")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
    update_coordinator = types.ModuleType(
        "homeassistant.helpers.update_coordinator"
    )

    class SensorDeviceClass:
        DATE = "date"

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        key: str
        name: str | None = None
        translation_key: str | None = None
        native_unit_of_measurement: str | None = None
        device_class: str | None = None

    class SensorEntity:
        pass

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    class CoordinatorEntity:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs):
            pass

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorEntity = SensorEntity
    sensor.SensorEntityDescription = SensorEntityDescription
    config_entries.ConfigEntry = ConfigEntry
    const.PERCENTAGE = "%"
    core.HomeAssistant = HomeAssistant
    entity_platform.AddEntitiesCallback = object
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    components.sensor = sensor
    helpers.entity_platform = entity_platform
    helpers.update_coordinator = update_coordinator
    homeassistant.components = components
    homeassistant.config_entries = config_entries
    homeassistant.const = const
    homeassistant.core = core
    homeassistant.helpers = helpers

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.sensor"] = sensor
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.const"] = const
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
