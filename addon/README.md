# MagicLight Add-on for Home Assistant

MagicLight Add-on provides intelligent adaptive lighting control that automatically adjusts your lights based on the sun's position throughout the day.

## Features

- **Automatic Light Control**: Responds to ZHA switch button presses to control lights in the same area
- **Adaptive Lighting**: Adjusts color temperature and brightness based on sun elevation
- **Multi-Protocol Support**: Controls ZigBee, Z-Wave, WiFi, and Matter lights
- **ZHA Group Management**: Automatically creates and syncs ZigBee groups for efficient control
- **Light Designer**: Built-in web interface for customizing adaptive lighting curves
- **Magic Mode**: Lights automatically update when physical switches are used
- **Energy Efficient**: Optimized group control reduces ZigBee network traffic

## Installation

1. Add the MagicLight repository to your Home Assistant:
   - Navigate to **Settings** → **Add-ons** → **Add-on Store**
   - Click the three dots menu → **Repositories**
   - Add: `https://github.com/dtconceptsnc/magiclight`

2. Install the MagicLight add-on:
   - Find "MagicLight" in the add-on store
   - Click **Install**

3. Start the add-on:
   - Click **Start**
   - Check **Show in sidebar** for easy access to Light Designer

## Configuration

### Add-on Options

```yaml
manage_integration: true    # Keep the bundled MagicLight integration in sync automatically
manage_blueprints: true     # Auto-apply the Hue Dimmer blueprint to supported switches
```

- `manage_integration` keeps the MagicLight custom integration deployed in `/config/custom_components`.
- `manage_blueprints` scans for compatible Hue dimmer switches and creates managed automations per area that contain lights.
- Color handling (color mode, temperature range, curves) is managed from the Light Designer UI.

### Light Designer

Access the Light Designer through the Home Assistant sidebar when the add-on is running:

1. **Morning Curve**: Configure how lights transition from sunrise to midday
   - Adjust midpoint and steepness
   - Set brightness range

2. **Evening Curve**: Configure sunset to nighttime transitions
   - Customize warmth progression
   - Fine-tune dimming behavior

3. **Color Output**: Choose how MagicLight drives your fixtures
   - `kelvin` for color temperature commands (default)
   - `rgb` for direct RGB output
   - `xy` for CIE xy coordinates on capable lights

4. **Color Temperature**: Set the range from warm to cool
   - Minimum: Warmest evening light
   - Maximum: Brightest daylight

5. **Preview**: See real-time visualization of your settings
   - Current sun position indicator
   - Step markers for dimming levels

## How It Works

### Switch Integration

When you press a ZHA-compatible switch:
1. MagicLight detects the button press event
2. Identifies all lights in the same area as the switch
3. Calculates optimal lighting based on current sun position
4. Updates all lights with adaptive values

### Switch Integration

MagicLight supports Philips Hue Dimmer Switches via the included blueprint. The add-on copies it into `/config/blueprints/automation/magiclight` on startup so it is ready for use without manual import. Other switches require custom automations using the MagicLight integration services.

### Light Control

MagicLight controls all Home Assistant light entities including ZigBee, Z-Wave, WiFi, and Matter lights. For ZigBee lights, it automatically creates and manages efficient group commands.

### ZHA Group Management

MagicLight automatically manages ZigBee groups for optimal performance:
- Creates groups with "Magic_" prefix in a dedicated area
- Syncs group membership when devices change areas
- Uses efficient group commands for all-ZigBee areas
- Falls back to area control for mixed-protocol setups

## Advanced Usage

### Manual Testing

Test adaptive lighting for any area:
```bash
# Via Home Assistant CLI
ha addon logs magiclight --follow
```

### Monitoring

View real-time activity:
- Check add-on logs for event processing
- Monitor Light Designer for current sun position
- Watch for "Magic mode" updates in logs

### Performance Optimization

- ZigBee-only areas use group commands (single network packet)
- Mixed areas use parallel commands for responsiveness
- Automatic caching of device registry for fast lookups

## Troubleshooting

### Lights Not Responding

1. Verify the switch and lights are in the same area
2. Check that lights support color temperature adjustment
3. Ensure Home Assistant can control the lights directly
4. Review add-on logs for error messages

### Switch Not Detected

1. Confirm switch uses ZHA integration (not Zigbee2MQTT)
2. Check switch is properly paired and shows events
3. Verify button mapping in Developer Tools → Events

### Color Issues

1. Open the Light Designer and switch the **Color Output** mode
2. Try different modes: kelvin → rgb → xy
3. Check light capabilities in Home Assistant

## Technical Details

### WebSocket Connection
- Uses Home Assistant supervisor authentication
- Persistent connection with automatic reconnection
- Subscribes to ZHA events and state changes

### Adaptive Algorithm
- Solar position: -1 (sunrise) to 0 (noon) to 1 (sunset)
- Separate morning/evening curves with midpoint control
- Brightness steps: 10%, 30%, 50%, 70%, 100%
- Color temperature interpolation based on sun elevation

### File Structure
```
/addon/
├── main.py              # WebSocket client and event handler
├── brain.py             # Adaptive lighting calculations
├── light_controller.py  # Multi-protocol light control
├── switch.py           # Switch command processing
├── webserver.py        # Light Designer server
├── designer.html       # Light Designer interface
└── config.yaml         # Add-on metadata
```

## Support

For issues or feature requests, please visit:
https://github.com/dtconceptsnc/magiclight/issues

## License

GNU General Public License v3.0
