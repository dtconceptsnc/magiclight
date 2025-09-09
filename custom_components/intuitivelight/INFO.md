# Intuitive Light

## Features

This integration provides services to control the Intuitive Light addon for Home Assistant.

### Services

- **`intuitivelight.step_up`** - Increase brightness by one step along the adaptive lighting curve
- **`intuitivelight.step_down`** - Decrease brightness by one step along the adaptive lighting curve

## Requirements

This integration requires the Intuitive Light addon to be installed and running.

## Installation

1. Install via HACS or manually copy the `custom_components/intuitivelight` folder to your Home Assistant configuration
2. Restart Home Assistant
3. Go to Settings → Integrations → Add Integration → Search for "Intuitive Light"
4. Follow the configuration steps

## Usage

Once installed, you can use the services in your automations:

```yaml
service: intuitivelight.step_up
data:
  area_id: living_room
```

```yaml
service: intuitivelight.step_down
data:
  area_id: bedroom
```