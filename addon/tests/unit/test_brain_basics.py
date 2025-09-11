from datetime import datetime

from brain import (
    get_adaptive_lighting,
    AdaptiveLighting,
    calculate_dimming_step,
)


SF = dict(latitude=37.7749, longitude=-122.4194, timezone="America/Los_Angeles")


def test_get_adaptive_lighting_basic_ranges():
    now = datetime(2024, 6, 21, 12, 0, 0)  # noon solstice, deterministic
    result = get_adaptive_lighting(current_time=now, **SF)

    # Expected keys present
    for key in ("kelvin", "brightness", "rgb", "xy", "sun_position", "solar_time"):
        assert key in result

    # Ranges: defaults are 500–6500K and 1–100%
    assert 500 <= result["kelvin"] <= 6500
    assert 1 <= result["brightness"] <= 100

    # Color representations look sane
    r, g, b = result["rgb"]
    assert all(0 <= c <= 255 for c in (r, g, b))
    x, y = result["xy"]
    assert 0 <= x <= 1 and 0 <= y <= 1


def test_color_conversion_roundtrips_in_ranges():
    al = AdaptiveLighting()
    for kelvin in (2000, 3000, 4000, 5000, 6500):
        x, y = al.color_temperature_to_xy(kelvin)
        assert 0 <= x <= 1 and 0 <= y <= 1
        r, g, b = al.color_temperature_to_rgb(kelvin)
        assert all(0 <= c <= 255 for c in (r, g, b))


def test_calculate_dimming_step_has_target_time():
    now = datetime(2024, 6, 21, 19, 0, 0)  # evening
    out = calculate_dimming_step(current_time=now, action="dim", **SF)
    assert "target_time" in out and out["target_time"] != now
    assert "time_offset_minutes" in out
    assert 500 <= out["kelvin"] <= 6500
    assert 1 <= out["brightness"] <= 100


def test_brightness_and_cct_vary_over_day():
    al = AdaptiveLighting(
        solar_midnight=datetime(2024, 1, 1, 0, 0, 0),
        solar_noon=datetime(2024, 1, 1, 12, 0, 0),
    )
    morning = datetime(2024, 1, 1, 9, 0, 0)
    evening = datetime(2024, 1, 1, 21, 0, 0)
    bri_m = al.calculate_brightness(morning)
    bri_e = al.calculate_brightness(evening)
    cct_m = al.calculate_color_temperature(morning)
    cct_e = al.calculate_color_temperature(evening)
    # They should not be identical across halves
    assert bri_m != bri_e or cct_m != cct_e

