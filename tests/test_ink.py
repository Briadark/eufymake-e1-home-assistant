from pyeufymake.ink import find_ink_status, iter_status_messages, parse_ink_status


def test_iter_status_messages_accepts_single_message() -> None:
    message = {"commandType": 1100}

    assert iter_status_messages(message) == (message,)


def test_iter_status_messages_filters_batch() -> None:
    payload = [{"commandType": 1000}, "bad", {"commandType": 1100}]

    assert iter_status_messages(payload) == (
        {"commandType": 1000},
        {"commandType": 1100},
    )


def test_find_ink_status_from_batched_payload() -> None:
    payload = [
        {"commandType": 1000, "state": 0},
        _ink_status_message(),
    ]

    status = find_ink_status(payload)

    assert status is not None
    assert len(status.channels) == 6
    assert status.channels[0].channel == "C"
    assert status.channels[0].remaining_percent == 78.2
    assert status.channels[4].channel == "W"
    assert status.channels[4].expired is False
    assert status.waste_tank is not None
    assert status.waste_tank.remaining_percent == 20.0
    assert status.waste_tank.distance_expiration_days == 402


def test_parse_ink_status_without_waste_tank() -> None:
    status = parse_ink_status({"commandType": 1100, "ink": {"leftInk": [100]}})

    assert len(status.channels) == 1
    assert status.channels[0].channel == "1"
    assert status.channels[0].remaining_percent == 1.0
    assert status.waste_tank is None


def _ink_status_message() -> dict:
    return {
        "commandType": 1100,
        "ink": {
            "count": 6,
            "colorSort": ["C", "M", "Y", "K", "W", "G"],
            "leftInk": [7820, 7730, 7869, 7639, 6261, 7133],
            "sn": [
                "AR480000000000001",
                "AR480100000000001",
                "AR480200000000001",
                "AR480300000000001",
                "AR480400000000001",
                "AR480500000000001",
            ],
            "status": [1, 1, 1, 1, 1, 1],
            "expirationTimestamp": [
                1790697600,
                1790697601,
                1790697602,
                1790697603,
                1790697604,
                1790697605,
            ],
            "distanceExpiration": [164, 164, 164, 164, 283, 280],
            "expired": [0, 0, 0, 0, 0, 0],
        },
        "wasteInk": {
            "count": 1,
            "leftInk": [2000],
            "status": [1],
            "expirationTimestamp": [1800000000],
            "distanceExpiration": [402],
            "expired": [0],
        },
    }
