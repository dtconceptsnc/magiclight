# HomeGlo

## Features

This integration provides services to control the HomeGlo addon for Home Assistant.

### Services

- **`homeglo.step_up`** - Increase brightness by one step along the adaptive lighting curve
- **`homeglo.step_down`** - Decrease brightness by one step along the adaptive lighting curve

## Requirements

This integration requires the HomeGlo addon to be installed and running.

## Installation

1. Install via HACS or manually copy the `custom_components/homeglo` folder to your Home Assistant configuration
2. Restart Home Assistant
3. Go to Settings → Integrations → Add Integration → Search for "HomeGlo"
4. Follow the configuration steps

## Usage

Once installed, you can use the services in your automations:

```yaml
service: homeglo.step_up
data:
  area_id: living_room
```

```yaml
service: homeglo.step_down
data:
  area_id: bedroom
```
