# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview
MagicLight is a Home Assistant add-on that connects to the Home Assistant WebSocket API and listens for ZHA switch events. When a switch's top button is pressed, it automatically turns on lights in the corresponding area with adaptive lighting based on the sun's position.

## Architecture

### Core Components
- `magiclight/main.py`: WebSocket client that connects to Home Assistant, handles authentication, subscribes to events, and processes ZHA switch button presses
- `magiclight/brain.py`: Adaptive lighting calculator that determines color temperature and brightness based on sun position

### Key Functionality
1. **WebSocket Connection**: Establishes persistent connection to Home Assistant using long-lived access token
2. **Device Discovery**: Maps ZHA switch devices to their areas through Home Assistant's device registry
3. **Event Handling**: Listens for ZHA button press events (specifically top button "on_press" commands)
4. **Adaptive Lighting**: Calculates appropriate lighting values based on sun elevation data from Home Assistant

## Development Commands

### Local Testing
```bash
# Test Python app directly (requires .env file)
cd magiclight
./test_local.sh

# Build addon for current architecture (no cache)
./build_local.sh

# Build and run locally
./build_local.sh --run
```

### Building Add-on
```bash
# Build for specific architecture
./build_addon.sh --arch amd64

# Build for all architectures
./build_addon.sh --all

# Build without cache
./build_addon.sh --no-cache
```

### Python Dependencies
```bash
# Install requirements
pip3 install -r magiclight/requirements.txt
```

## Configuration

### Environment Variables (for local testing)
- `HA_HOST`: Home Assistant host (default: localhost)
- `HA_PORT`: Home Assistant port (default: 8123)
- `HA_TOKEN`: Long-lived access token (required)
- `HA_USE_SSL`: Use SSL connection (default: false)
- `HA_WEBSOCKET_URL`: Full WebSocket URL (overrides host/port)

### Add-on Configuration
The add-on uses Home Assistant's auth_api and homeassistant_api for automatic authentication when running as an add-on.

## Key Design Patterns

### Event Processing Flow
1. WebSocket receives ZHA event with device_id, command, and button info
2. Device ID is mapped to area using pre-loaded device registry data
3. Sun position is calculated from cached sun entity state
4. Adaptive lighting values are computed (color temp, brightness, RGB, XY)
5. Light service is called for all lights in the target area

### Adaptive Lighting Algorithm
- Uses sun elevation to determine position (-1 to 1 scale)
- Interpolates color temperature between 2000K (warm) and 5500K (cool)
- Adjusts brightness based on sun position (10-100%)
- Converts color temperature to RGB and XY coordinates for compatibility

## Testing Considerations
- The add-on can be tested locally using Docker or directly with Python
- Use `--test` flag with build_addon.sh for test mode builds
- Monitor logs for device discovery, event handling, and adaptive lighting calculations

## GIT
- When asked to create a commit always: bump version in config.yaml, and add to changelog