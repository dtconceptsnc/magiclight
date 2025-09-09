# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview
Intuitive Light is a Home Assistant add-on that connects to the Home Assistant WebSocket API and listens for ZHA switch events. When a switch's top button is pressed, it automatically turns on lights in the corresponding area with adaptive lighting based on the sun's position.

## Architecture

### Core Components
- `addon/main.py`: WebSocket client that connects to Home Assistant, handles authentication, subscribes to events, and processes ZHA switch button presses
- `addon/brain.py`: Adaptive lighting calculator that determines color temperature and brightness based on sun position and configurable curves
- `addon/light_controller.py`: Multi-protocol light controller with support for ZigBee, Z-Wave, WiFi, Matter
- `addon/switch.py`: Switch command processor handling button press events and light control
- `addon/webserver.py`: Web server for Light Designer interface accessible via Home Assistant ingress

### Key Functionality
1. **WebSocket Connection**: Establishes persistent connection to Home Assistant using long-lived access token
2. **Device Discovery**: Maps ZHA switch devices to their areas through Home Assistant's device registry
3. **Event Handling**: Listens for ZHA button press events (specifically top button "on_press" commands)
4. **Adaptive Lighting**: Calculates appropriate lighting values based on sun elevation data from Home Assistant
5. **Magic Mode**: Automatically updates lights in areas where switches have been used
6. **Light Designer**: Web interface for configuring adaptive lighting curves

## Development Commands

### Testing
```bash
# Run tests with coverage
pytest tests/ --cov=addon --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_brain_basics.py

# Run with verbose output
pytest -v tests/
```

### Local Development
```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Build addon for current architecture (no cache)
cd addon && ./build_local.sh

# Build and run locally with web UI on port 8099
cd addon && ./build_local.sh --run

# Build and run on custom port
cd addon && ./build_local.sh --run --port 8100
```

### Building Add-on
```bash
# Build for specific architecture
cd addon && ./build_addon.sh --arch amd64

# Build for all architectures
cd addon && ./build_addon.sh --all

# Build without cache
cd addon && ./build_addon.sh --no-cache

# Build and push to registry
cd addon && ./build_addon.sh --push
```

## Configuration

### Environment Variables (for local testing)
Create `addon/.env` file:
```
HA_HOST=localhost
HA_PORT=8123
HA_TOKEN=your_long_lived_token_here
HA_USE_SSL=false
COLOR_MODE=kelvin
```

### Add-on Configuration
The add-on uses Home Assistant's auth_api and homeassistant_api for automatic authentication when running as an add-on.

Configuration options in Home Assistant:
- `color_mode`: Choose between kelvin, rgb, or xy color modes
- `min_color_temp`: Minimum color temperature in Kelvin (default: 500)
- `max_color_temp`: Maximum color temperature in Kelvin (default: 6500)

## Key Design Patterns

### Event Processing Flow
1. WebSocket receives ZHA event with device_id, command, and button info
2. Device ID is mapped to area using pre-loaded device registry data
3. Sun position is calculated from cached sun entity state
4. Adaptive lighting values are computed (color temp, brightness, RGB, XY)
5. Light service is called for all lights in the target area

### Adaptive Lighting Algorithm
- Uses solar time to determine position (-1 to 1 scale)
- Separate morning and evening curves with configurable parameters
- Midpoint and steepness controls for fine-tuning transitions
- Step-based dimming along the adaptive curve
- Converts color temperature to RGB and XY coordinates for compatibility

### ZHA Group Management
- Automatically creates/syncs ZHA groups with "Glo_" prefix
- Groups organized in dedicated "Glo_Zigbee_Groups" area
- Smart light control method selection based on area composition
- Areas with only ZHA lights use efficient group control
- Mixed-protocol areas use area-based control

## Light Designer Interface
- Accessible through Home Assistant sidebar when addon is running
- Interactive graph showing real-time preview of lighting curves
- Visual controls for curve parameters with live updates
- Save configuration directly from the web interface
- API endpoints at `/api/config` (GET) and `/api/save` (POST)

## Testing Considerations
- The add-on can be tested locally using Docker or directly with Python
- Use `--test` flag with build_addon.sh for test mode builds
- Monitor logs for device discovery, event handling, and adaptive lighting calculations
- Test files organized in `tests/unit/` directory

## Git Workflow
When creating commits:
1. Update version in `addon/config.yaml`
2. Add entry to `addon/CHANGELOG.md`
3. Include descriptive commit message
4. Use conventional commit format when applicable