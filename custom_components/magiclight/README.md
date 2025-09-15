# MagicLight Integration for Home Assistant

The MagicLight custom integration provides Home Assistant services for controlling lights with adaptive lighting based on the sun's position. It works in conjunction with the MagicLight add-on to provide flexible automation capabilities.

## Prerequisites

**Important**: The MagicLight integration requires the MagicLight add-on to be installed and running. The add-on handles adaptive lighting calculations, sun position tracking, and light control logic.

## Installation

### Via HACS (Recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dtconceptsnc&repository=magiclight&category=integration)

1. Click the button above or search for "MagicLight" in HACS
2. Install and restart Home Assistant
3. Add the integration: **Settings** → **Devices & Services** → **+ Add Integration** → "MagicLight"

### Manual Installation

1. Copy `custom_components/magiclight` to your Home Assistant's `custom_components` directory
2. Restart Home Assistant and add the integration

## Available Services

### `magiclight.magiclight_on`
Enable MagicLight mode and set lights to current time position with adaptive values.

### `magiclight.magiclight_off`  
Disable MagicLight mode without changing light state. Saves current time offset for later restoration.

### `magiclight.magiclight_toggle`
Smart toggle based on light state. If lights are on, turns them off and disables MagicLight. If lights are off, enables MagicLight and turns them on with adaptive values.

### `magiclight.step_up`
Increase brightness by one step along the adaptive lighting curve (brightens and cools).

### `magiclight.step_down`
Decrease brightness by one step along the adaptive lighting curve (dims and warms).

### `magiclight.reset`
Reset time offset to current time, enable MagicLight, and apply current adaptive lighting.

**Service Data (all services):**
```yaml
area_id: living_room  # Target area (required)
```

## Basic Usage Example

```yaml
automation:
  - alias: "Toggle Living Room Lights"
    trigger:
      - platform: device
        device_id: YOUR_SWITCH_ID
        domain: zha
        type: remote_button_short_press
        subtype: turn_on
    action:
      - service: magiclight.magiclight_toggle
        data:
          area_id: living_room
```

## Support

For issues or questions: [GitHub Issues](https://github.com/dtconceptsnc/magiclight/issues)

## License

GNU General Public License v3.0