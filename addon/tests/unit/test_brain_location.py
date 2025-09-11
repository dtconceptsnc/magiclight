import os
from datetime import datetime

import pytest

from brain import get_adaptive_lighting


def test_get_adaptive_lighting_raises_without_location(monkeypatch):
    # Ensure env vars are absent
    for k in [
        "HASS_LATITUDE",
        "HASS_LONGITUDE",
        "LATITUDE",
        "LONGITUDE",
        "HASS_TIME_ZONE",
        "TZ",
    ]:
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(ValueError):
        get_adaptive_lighting(current_time=datetime(2024, 1, 1, 12, 0, 0))


def test_get_adaptive_lighting_uses_env_vars(monkeypatch):
    # Provide HA-style env vars
    monkeypatch.setenv("HASS_LATITUDE", "37.7749")
    monkeypatch.setenv("HASS_LONGITUDE", "-122.4194")
    monkeypatch.setenv("HASS_TIME_ZONE", "UTC")

    out = get_adaptive_lighting(current_time=datetime(2024, 6, 21, 12, 0, 0))
    assert 500 <= out["kelvin"] <= 6500
    assert 1 <= out["brightness"] <= 100

