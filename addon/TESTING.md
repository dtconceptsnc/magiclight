# Testing HomeGlo

## Setup

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run with coverage
```bash
pytest --cov=homeglo --cov-report=html
```
Then open `htmlcov/index.html` to view coverage report.

### Run specific test file
```bash
pytest tests/unit/test_new_algorithm.py
```

### Run specific test class or method
```bash
pytest tests/unit/test_new_algorithm.py::TestSimplifiedAdaptiveLighting
pytest tests/unit/test_new_algorithm.py::TestSimplifiedAdaptiveLighting::test_noon_values
```

### Run with verbose output
```bash
pytest -v
```

### Run and stop on first failure
```bash
pytest -x
```

## Test Files

The test suite includes:

- `tests/unit/test_brain_basics.py` - Basic brain module functionality
- `tests/unit/test_brain_color.py` - Color temperature conversions
- `tests/unit/test_brain_location.py` - Location handling
- `tests/unit/test_brain_solar_time.py` - Solar time calculations
- `tests/unit/test_dimming.py` - Dimming step calculations
- `tests/unit/test_new_algorithm.py` - New simplified curves and arc-based dimming
- `tests/unit/test_zha_parity.py` - ZHA integration tests

## Writing Tests

Tests use pytest. Basic structure:

```python
import pytest
from homeglo.brain import get_adaptive_lighting

def test_something():
    result = get_adaptive_lighting(...)
    assert result['brightness'] > 0

class TestFeature:
    def test_aspect_one(self):
        assert True
    
    def test_aspect_two(self):
        assert True
```

Use fixtures for shared test data:

```python
@pytest.fixture
def test_config():
    return {
        'mid_bri_up': 6.0,
        'steep_bri_up': 1.5,
        # ...
    }

def test_with_config(test_config):
    result = get_adaptive_lighting(config=test_config)
    assert result is not None
```