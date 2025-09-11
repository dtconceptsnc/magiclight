# HomeGlo Integration for Home Assistant

The HomeGlo custom integration provides Home Assistant services for controlling lights with adaptive lighting based on the sun's position. It works in conjunction with the HomeGlo add-on to provide flexible automation capabilities.

## Features

- **Service-Based Control**: Exposes services that can be called from automations
- **Flexible Triggers**: Works with any Home Assistant trigger (not limited to ZHA)
- **Area-Based Control**: Target specific areas or let the system determine from device context
- **Adaptive Stepping**: Increase or decrease brightness along the adaptive curve
- **WebSocket Communication**: Real-time communication with the HomeGlo add-on

## Installation

### Via HACS (Recommended)

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=intuitivelight&repository=homeglo-ha&category=integration)

1. Ensure [HACS](https://hacs.xyz/) is installed in your Home Assistant
2. Click the button above or:
   - Open HACS in Home Assistant
   - Go to **Integrations**
   - Click the **+** button
   - Search for "HomeGlo"
3. Click **Download**
4. Restart Home Assistant
5. Add the integration:
   - Go to **Settings** → **Devices & Services**
   - Click **+ Add Integration**
   - Search for "HomeGlo"

### Manual Installation

1. Copy the `custom_components/homeglo` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant
3. Add the integration through the UI as described above

## Prerequisites

The HomeGlo integration requires the HomeGlo add-on to be installed and running. The add-on handles:
- Adaptive lighting calculations
- Sun position tracking
- Light control logic

## Available Services

### `homeglo.step_up`

Increase brightness by one step along the adaptive lighting curve.

**Service Data:**
```yaml
area_id: living_room  # Optional: Target area
device_id: abc123     # Optional: Triggering device
```

### `homeglo.step_down`

Decrease brightness by one step along the adaptive lighting curve.

**Service Data:**
```yaml
area_id: bedroom      # Optional: Target area
device_id: def456     # Optional: Triggering device
```

## Automation Examples

### Basic Switch Control

Control lights with a smart switch:

```yaml
automation:
  - alias: "Kitchen - Brightness Up"
    trigger:
      - platform: device
        device_id: YOUR_SWITCH_ID
        domain: zha
        type: remote_button_short_press
        subtype: dim_up
    action:
      - service: homeglo.step_up
        data:
          area_id: kitchen

  - alias: "Kitchen - Brightness Down"
    trigger:
      - platform: device
        device_id: YOUR_SWITCH_ID
        domain: zha
        type: remote_button_short_press
        subtype: dim_down
    action:
      - service: homeglo.step_down
        data:
          area_id: kitchen
```

### Motion-Activated Lighting

Turn on lights with adaptive settings when motion is detected:

```yaml
automation:
  - alias: "Hallway Motion Lights"
    trigger:
      - platform: state
        entity_id: binary_sensor.hallway_motion
        to: "on"
    action:
      - service: homeglo.step_up
        data:
          area_id: hallway
```

### Time-Based Adjustments

Gradually brighten lights in the morning:

```yaml
automation:
  - alias: "Morning Wake Up"
    trigger:
      - platform: time_pattern
        minutes: "/10"
    condition:
      - condition: time
        after: "06:00:00"
        before: "07:00:00"
    action:
      - service: homeglo.step_up
        data:
          area_id: bedroom
```

### Voice Assistant Integration

Use with voice commands via Google Assistant or Alexa:

```yaml
automation:
  - alias: "Voice - Dim Living Room"
    trigger:
      - platform: event
        event_type: assistant_command
        event_data:
          text: "dim the living room"
    action:
      - service: homeglo.step_down
        data:
          area_id: living_room
```

### Scene Integration

Include in scenes for consistent lighting:

```yaml
scene:
  - name: "Evening Relaxation"
    entities:
      # Other entities...
    - service: homeglo.step_down
      data:
        area_id: living_room
```

## Advanced Usage

### Dynamic Area Selection

Use templates to dynamically select areas:

```yaml
automation:
  - alias: "Dynamic Light Control"
    trigger:
      - platform: event
        event_type: custom_button_press
    action:
      - service: homeglo.step_up
        data:
          area_id: "{{ trigger.event.data.area }}"
```

### Conditional Brightness

Adjust based on conditions:

```yaml
automation:
  - alias: "Adaptive Brightness by Time"
    trigger:
      - platform: state
        entity_id: binary_sensor.presence
        to: "on"
    action:
      - choose:
          - conditions:
              - condition: time
                before: "12:00:00"
            sequence:
              - service: homeglo.step_up
                data:
                  area_id: office
          - conditions:
              - condition: time
                after: "20:00:00"
            sequence:
              - service: homeglo.step_down
                data:
                  area_id: office
```

## How It Works

1. **Service Call**: When you call a HomeGlo service from an automation
2. **WebSocket Event**: The integration sends an event to the HomeGlo add-on
3. **Processing**: The add-on calculates adaptive values based on sun position
4. **Light Control**: The add-on updates the specified lights
5. **Confirmation**: The integration receives confirmation of the action

## Troubleshooting

### Services Not Available

1. Ensure the HomeGlo add-on is installed and running
2. Check the integration is properly configured
3. Restart Home Assistant after installation

### Lights Not Responding

1. Verify the area_id matches an existing area in Home Assistant
2. Check that lights in the area support color temperature
3. Review HomeGlo add-on logs for errors

### Integration Not Loading

1. Check Home Assistant logs for error messages
2. Verify the custom_components folder structure
3. Ensure you've restarted after installation

## Developer Information

The integration communicates with the HomeGlo add-on via WebSocket events:

**Event Structure:**
```python
{
    "type": "homeglo_command",
    "command": "step_up" | "step_down",
    "area_id": "optional_area",
    "device_id": "optional_device"
}
```

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/intuitivelight/homeglo-ha/issues
- Home Assistant Community: https://community.home-assistant.io/

## License

GNU General Public License v3.0