from datetime import datetime, timedelta

from brain import AdaptiveLighting


def test_calculate_sun_position_cosine_at_key_points():
    noon = datetime(2024, 1, 1, 12, 0, 0)
    midnight = noon - timedelta(hours=12)
    al = AdaptiveLighting(solar_noon=noon, solar_midnight=midnight)

    # At solar noon → +1
    assert abs(al.calculate_sun_position(noon, 0.0) - 1.0) < 1e-6
    # At solar midnight → -1
    assert abs(al.calculate_sun_position(midnight, 0.0) - (-1.0)) < 1e-6
    # 6h from noon → 0
    six_am = noon - timedelta(hours=6)
    six_pm = noon + timedelta(hours=6)
    assert abs(al.calculate_sun_position(six_am, 0.0)) < 1e-6
    assert abs(al.calculate_sun_position(six_pm, 0.0)) < 1e-6


def test_get_solar_time_wraps_and_aligns():
    noon = datetime(2024, 1, 1, 12, 0, 0)
    midnight = noon - timedelta(hours=12)
    al = AdaptiveLighting(solar_noon=noon, solar_midnight=midnight)

    assert abs(al.get_solar_time(midnight) - 0.0) < 1e-6
    assert abs(al.get_solar_time(noon) - 12.0) < 1e-6
    assert abs(al.get_solar_time(midnight + timedelta(hours=24)) - 0.0) < 1e-6


def test_get_solar_time_fallback_without_solar_refs():
    al = AdaptiveLighting()
    now = datetime(2024, 1, 1, 9, 30, 0)
    assert abs(al.get_solar_time(now) - 9.5) < 1e-9

