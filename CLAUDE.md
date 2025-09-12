# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview
MagicLight (formerly Intuitive Light) is a dual-component Home Assistant project:
1. **Add-on** (`addon/`): Docker-based Home Assistant add-on that provides adaptive lighting based on sun position
2. **Custom Integration** (`custom_components/magiclight/`): HACS-installable integration providing MagicLight service primitives

The add-on connects to Home Assistant's WebSocket API, listens for ZHA switch events, and automatically adjusts lights in corresponding areas with adaptive lighting based on the sun's position.

## Architecture

### Core Components
- `addon/main.py`: WebSocket client that connects to Home Assistant, handles authentication, subscribes to events, and processes ZHA switch button presses
- `addon/brain.py`: Adaptive lighting calculator that determines color temperature and brightness based on sun position and configurable curves
- `addon/light_controller.py`: Multi-protocol light controller with support for ZigBee, Z-Wave, WiFi, Matter
- `addon/switch.py`: Switch command processor handling button press events and light control
- `addon/webserver.py`: Web server for Light Designer interface accessible via Home Assistant ingress
- `addon/designer.html`: Interactive web UI for configuring adaptive lighting curves
- `addon/primitives.py`: Core service implementations for MagicLight operations

### Key Functionality
1. **WebSocket Connection**: Establishes persistent connection to Home Assistant using long-lived access token
2. **Device Discovery**: Maps ZHA switch devices to their areas through Home Assistant's device registry
3. **Event Handling**: Listens for ZHA button press events (specifically "on_press" commands)
4. **Adaptive Lighting**: Calculates appropriate lighting values based on sun elevation data from Home Assistant
5. **Magic Mode**: Automatically updates lights in areas where switches have been used
6. **Light Designer**: Web interface for configuring adaptive lighting curves
7. **ZHA Group Management**: Automatically creates/syncs ZHA groups with "Magic_" prefix for efficient control
8. **Service Primitives**: Provides `magiclight_on`, `magiclight_off`, `magiclight_toggle`, `step_up`, `step_down`, and `reset` services

## Development Commands

### Testing
```bash
# Run tests with coverage
pytest tests/ --cov=addon --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_brain_basics.py

# Run with verbose output
pytest -v tests/

# Run and stop on first failure
pytest -x
```

### Local Development
```bash
# Install development dependencies
pip install -r addon/requirements-dev.txt

# Build addon for current architecture (no cache)
cd addon && ./build_local.sh

# Build and run locally with web UI on port 8099
cd addon && ./build_local.sh --run

# Build and run on custom port
cd addon && ./build_local.sh --run --port 8100
```

## Configuration

### Environment Variables (for local testing)
Create `addon/.env` file:
```
HA_HOST=localhost
HA_PORT=8123
HA_TOKEN=your_long_lived_token_here
HA_USE_SSL=false
```

### Add-on Configuration
The add-on uses Home Assistant's auth_api and homeassistant_api for automatic authentication when running as an add-on.

Configuration option in Home Assistant:
- `color_mode`: Choose between kelvin, rgb, or xy color modes (default: kelvin)

### Repository Configuration
- `repository.yaml`: Defines the add-on repository metadata
- `hacs.json`: Configuration for HACS installation of the custom integration
- Repository URL: https://github.com/intuitivelight/homeglo-ha

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
- Automatically creates/syncs ZHA groups with "Magic_" prefix
- Groups organized in dedicated "Magic_Zigbee_Groups" area
- Smart light control method selection based on area composition
- Areas with only ZHA lights use efficient group control
- Mixed-protocol areas use area-based control
- Groups automatically update when devices change areas

## Light Designer Interface
- Accessible through Home Assistant sidebar when addon is running
- Interactive graph showing real-time preview of lighting curves
- Visual controls for curve parameters with live updates
- Save configuration directly from the web interface
- API endpoints at `/api/config` (GET) and `/api/save` (POST)
- Shows step markers when dimming visualization is enabled

## Testing Considerations
- The add-on can be tested locally using Docker or directly with Python
- Test files organized in `tests/unit/` directory covering core functionality
- Monitor logs for device discovery, event handling, and adaptive lighting calculations
- Use pytest for running tests (no pytest.ini file - uses defaults)

## Git Workflow
When creating commits:
1. Update version in `addon/config.yaml`
2. Add entry to `addon/CHANGELOG.md`
3. Include descriptive commit message
4. Use conventional commit format when applicable

## Blueprint Automation
The repository includes a Home Assistant blueprint (`blueprints/blueprint.yaml`) for easy switch automation:
- Supports multiple ZHA switch devices
- Targets multiple areas simultaneously
- ON button: Smart toggle (uses `magiclight_toggle` service)
- OFF button: Reset to current time
- UP/DOWN buttons: Step along adaptive curve

## Project Structure
```
/addon/                  # Home Assistant add-on
  ├── main.py           # WebSocket client and main entry point
  ├── brain.py          # Adaptive lighting calculations
  ├── light_controller.py # Multi-protocol light control
  ├── switch.py         # Switch event handling
  ├── primitives.py     # MagicLight service implementations
  ├── webserver.py      # Light Designer web server
  ├── designer.html     # Light Designer UI
  ├── config.yaml       # Add-on configuration
  ├── Dockerfile        # Container build
  ├── build.yaml        # Multi-arch build config
  └── build_local.sh    # Local development script

/custom_components/magiclight/  # HACS integration
  ├── __init__.py       # Service registration
  ├── manifest.json     # Integration metadata
  └── services.yaml     # Service definitions

/tests/unit/            # Test suite
  └── test_*.py         # Unit tests for core functionality

/blueprints/            # Home Assistant blueprints
  └── blueprint.yaml    # ZHA switch automation
```