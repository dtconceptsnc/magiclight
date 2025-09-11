from brain import AdaptiveLighting


def test_color_temperature_to_xy_and_rgb_ranges():
    al = AdaptiveLighting()
    for k in (1500, 2000, 3000, 4000, 5000, 6500):
        x, y = al.color_temperature_to_xy(k)
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0
        r, g, b = al.color_temperature_to_rgb(k)
        assert all(0 <= c <= 255 for c in (r, g, b))


def test_warmer_vs_cooler_rgb_trend():
    al = AdaptiveLighting()
    warm_rgb = al.color_temperature_to_rgb(2000)
    cool_rgb = al.color_temperature_to_rgb(6500)
    # Warmer tends to have more red than blue
    assert warm_rgb[0] > warm_rgb[2]
    # Cooler should have more blue than warm (not necessarily more than red at D65)
    assert cool_rgb[2] >= warm_rgb[2]


def test_xy_from_rgb_close_to_xy_from_kelvin():
    al = AdaptiveLighting()
    for k in (2200, 3000, 4000, 5000):
        x1, y1 = al.color_temperature_to_xy(k)
        r, g, b = al.color_temperature_to_rgb(k)
        x2, y2 = al.rgb_to_xy((r, g, b))
        # Allow loose tolerance; conversions aren't exact
        assert abs(x1 - x2) < 0.12
        assert abs(y1 - y2) < 0.12
