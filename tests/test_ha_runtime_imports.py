import importlib.util
import sys
import types
from pathlib import Path


COMPONENT_DIR = (
    Path(__file__).resolve().parents[1] / "custom_components" / "eufymake_e1"
)


def test_coordinator_imports_without_vendored_pyeufymake_package() -> None:
    _stub_homeassistant()
    package = types.ModuleType("custom_components.eufymake_e1")
    package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["custom_components.eufymake_e1"] = package
    sys.modules["custom_components.eufymake_e1.const"] = _load_real_const()
    sys.modules.pop("custom_components.eufymake_e1.pyeufymake", None)

    spec = importlib.util.spec_from_file_location(
        "custom_components.eufymake_e1.coordinator",
        COMPONENT_DIR / "coordinator.py",
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.EufyMakeE1Coordinator is not None


def test_coordinator_live_data_includes_ink_attributes() -> None:
    _stub_homeassistant()
    package = types.ModuleType("custom_components.eufymake_e1")
    package.__path__ = [str(COMPONENT_DIR)]
    sys.modules["custom_components.eufymake_e1"] = package
    sys.modules["custom_components.eufymake_e1.const"] = _load_real_const()

    runtime = _load_module(
        "custom_components.eufymake_e1.runtime",
        COMPONENT_DIR / "runtime.py",
    )
    coordinator = _load_module(
        "custom_components.eufymake_e1.coordinator",
        COMPONENT_DIR / "coordinator.py",
    )

    data = coordinator._data_from_live_result(
        runtime.InkStatus(
            channels=(
                runtime.InkChannel(
                    channel="C",
                    remaining_percent=76.56,
                    status=1,
                    manufacture_timestamp=1756396800,
                    expiration_timestamp=1787932800,
                    distance_expiration_days=10,
                    expired=False,
                ),
            ),
            waste_tank=runtime.WasteInkTank(
                remaining_percent=20.0,
                status=1,
                expiration_timestamp=1803657600,
                distance_expiration_days=192,
                expired=False,
            ),
        ),
        decoded_messages=(
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1153, "attType": 4, "version": "V1.3.3"},
                command_type=1153,
            ),
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1118, "plateType": 3},
                command_type=1118,
            ),
        ),
        firmware_version="4.0.2",
        mqtt_online=True,
        p2p_online=None,
    )

    assert data["ink"]["C"] == 76.56
    assert data["ink_details"]["C"]["manufacture_date"] == "2025-08-28"
    assert data["ink_details"]["C"]["expiration_date"] == "2026-08-28"
    assert data["ink_details"]["C"]["days_until_expiration"] == 10
    assert data["ink_details"]["C"]["expired"] is False
    assert data["waste_ink_details"]["expiration_date"] == "2027-02-26"
    assert data["current_accessory"] == "Rotary Printing Attachment"
    assert data["current_accessory_details"] == {
        "attachment_type": 4,
        "plate_type": 3,
        "version": "V1.3.3",
    }


def test_runtime_accessory_status_uses_latest_plate_message() -> None:
    _stub_homeassistant()
    runtime = _load_module(
        "custom_components.eufymake_e1.runtime",
        COMPONENT_DIR / "runtime.py",
    )

    status = runtime.find_accessory_status(
        (
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1153, "attType": 0, "version": ""},
                command_type=1153,
            ),
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1118, "plateType": 0},
                command_type=1118,
            ),
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1153, "attType": 4, "version": "V1.3.3"},
                command_type=1153,
            ),
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1118, "plateType": 3},
                command_type=1118,
            ),
        )
    )

    assert status.name == "Rotary Printing Attachment"
    assert status.attachment_type == 4
    assert status.plate_type == 3
    assert status.version == "V1.3.3"


def test_runtime_accessory_status_maps_standard_flatbed() -> None:
    _stub_homeassistant()
    runtime = _load_module(
        "custom_components.eufymake_e1.runtime",
        COMPONENT_DIR / "runtime.py",
    )

    status = runtime.find_accessory_status(
        (
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1118, "plateType": 2},
                command_type=1118,
            ),
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1153, "attType": 1, "version": ""},
                command_type=1153,
            ),
        )
    )

    assert status.name == "Standard Flatbed"
    assert status.attachment_type == 1
    assert status.plate_type == 2
    assert status.version == ""


def test_runtime_accessory_status_maps_none() -> None:
    _stub_homeassistant()
    runtime = _load_module(
        "custom_components.eufymake_e1.runtime",
        COMPONENT_DIR / "runtime.py",
    )

    status = runtime.find_accessory_status(
        (
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1118, "plateType": 1},
                command_type=1118,
            ),
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1153, "attType": 2, "version": "V1.2.1"},
                command_type=1153,
            ),
        )
    )

    assert status.name == "None"
    assert status.attachment_type == 2
    assert status.plate_type == 1
    assert status.version == "V1.2.1"


def test_runtime_accessory_status_maps_roll_to_film() -> None:
    _stub_homeassistant()
    runtime = _load_module(
        "custom_components.eufymake_e1.runtime",
        COMPONENT_DIR / "runtime.py",
    )

    status = runtime.find_accessory_status(
        (
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1153, "attType": 3, "version": "V1.1.16"},
                command_type=1153,
            ),
            runtime.DecodedMqttMessage(
                topic="/phone/maker/AKTEST/notice",
                variant="cbc",
                payload={"commandType": 1118, "plateType": 4},
                command_type=1118,
            ),
        )
    )

    assert status.name == "Roll-to-Film Attachment"
    assert status.attachment_type == 3
    assert status.plate_type == 4
    assert status.version == "V1.1.16"


def test_coordinator_preserves_previous_accessory_when_poll_lacks_accessory_packets() -> None:
    _stub_homeassistant()
    coordinator = _load_module(
        "custom_components.eufymake_e1.coordinator",
        COMPONENT_DIR / "coordinator.py",
    )

    data = {
        "current_accessory": None,
        "current_accessory_details": {
            "attachment_type": None,
            "plate_type": None,
            "version": None,
        },
    }
    coordinator._preserve_previous_accessory(
        data,
        {
            "current_accessory": "Roll-to-Film Attachment",
            "current_accessory_details": {
                "attachment_type": 3,
                "plate_type": 4,
                "version": "V1.1.16",
            },
        },
    )

    assert data["current_accessory"] == "Roll-to-Film Attachment"
    assert data["current_accessory_details"] == {
        "attachment_type": 3,
        "plate_type": 4,
        "version": "V1.1.16",
    }


def _load_real_const():
    return _load_module(
        "custom_components.eufymake_e1.const",
        COMPONENT_DIR / "const.py",
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
    config_entries = types.ModuleType("homeassistant.config_entries")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    update_coordinator = types.ModuleType(
        "homeassistant.helpers.update_coordinator"
    )

    class ConfigEntry:
        pass

    class HomeAssistant:
        pass

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs):
            pass

    class UpdateFailed(Exception):
        pass

    config_entries.ConfigEntry = ConfigEntry
    core.HomeAssistant = HomeAssistant
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.UpdateFailed = UpdateFailed
    helpers.update_coordinator = update_coordinator
    homeassistant.config_entries = config_entries
    homeassistant.core = core
    homeassistant.helpers = helpers

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator
