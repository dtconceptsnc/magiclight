# HomeGlo for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

HomeGlo provides adaptive lighting control for Home Assistant, automatically adjusting brightness and color temperature based on the sun's position.

## Components

This repository contains two components:

### 1. HomeGlo Addon (`addon/`)
A Home Assistant addon that:
- Connects to Home Assistant via WebSocket API
- Listens for ZHA switch events
- Provides adaptive lighting based on sun position
- Includes a Light Designer web interface for curve customization

### 2. HomeGlo Integration (`custom_components/homeglo/`)
A Home Assistant custom component that:
- Exposes services for controlling lights via automations
- Works with any trigger (not just ZHA switches)
- Communicates with the addon via WebSocket events

## Installation

### Installing the Addon

1. Add this repository to your Home Assistant addon store
2. Install the "HomeGlo" addon
3. Start the addon
4. Access the Light Designer through the Home Assistant sidebar

### Installing the Integration

#### Via HACS (Recommended)
1. Open HACS
2. Click on Integrations
3. Click the three dots menu and select "Custom repositories"
4. Add this repository URL with category "Integration"
5. Search for "HomeGlo" and install
6. Restart Home Assistant
7. Go to Settings → Integrations → Add Integration → Search for "HomeGlo"

#### Manual Installation
1. Copy the `custom_components/homeglo` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Integrations → Add Integration → Search for "HomeGlo"

## Services

The integration provides the following services:

### `homeglo.step_up`
Increase brightness by one step along the adaptive lighting curve.

**Parameters:**
- `area_id` (optional): The area to control
- `device_id` (optional): The device that triggered the command

### `homeglo.step_down`
Decrease brightness by one step along the adaptive lighting curve.

**Parameters:**
- `area_id` (optional): The area to control
- `device_id` (optional): The device that triggered the command

## Example Automations

### Control lights with a Zigbee button
```yaml
automation:
  - alias: "Living Room - Brightness Up"
    trigger:
      - platform: device
        device_id: YOUR_DEVICE_ID
        domain: zha
        type: remote_button_short_press
        subtype: dim_up
    action:
      - service: homeglo.step_up
        data:
          area_id: living_room

  - alias: "Living Room - Brightness Down"
    trigger:
      - platform: device
        device_id: YOUR_DEVICE_ID
        domain: zha
        type: remote_button_short_press
        subtype: dim_down
    action:
      - service: homeglo.step_down
        data:
          area_id: living_room
```

### Control with time-based automation
```yaml
automation:
  - alias: "Gradual Morning Brightening"
    trigger:
      - platform: time_pattern
        minutes: "/5"
    condition:
      - condition: time
        after: "06:00:00"
        before: "08:00:00"
    action:
      - service: homeglo.step_up
        data:
          area_id: bedroom
```

## Configuration

The adaptive lighting curves can be customized using the Light Designer interface accessible through the Home Assistant sidebar when the addon is running.

## Support

For issues, feature requests, or questions, please visit the [GitHub repository](https://github.com/intuitivelight/homeglo-ha).

## License

This project is licensed under the MIT License - see the LICENSE file for details.
