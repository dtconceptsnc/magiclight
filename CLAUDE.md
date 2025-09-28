# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview
MagicLight is a dual-component Home Assistant project:
1. **Add-on** (`addon/`): Docker-based Home Assistant add-on that provides adaptive lighting based on sun position
2. **Custom Integration** (`custom_components/magiclight/`): HACS-installable integration providing MagicLight service primitives

The add-on connects to Home Assistant's WebSocket API, listens for ZHA switch events, and automatically adjusts lights in corresponding areas with adaptive lighting based on the sun's position.

## Development Commands

### Testing
```bash
# Run tests with coverage (CI-compatible)
pytest --cov=magiclight --cov-report=term-missing

# Run tests with coverage (local development)
pytest addon/tests/ --cov=addon --cov-report=term-missing

# Run specific test file
pytest addon/tests/unit/test_brain_basics.py

# Run with verbose output
pytest -v addon/tests/

# Run and stop on first failure
pytest -x
```

### Linting and Formatting
```bash
# Format code with Black
black addon/*.py addon/tests/

# Check formatting without changes
black --check addon/*.py addon/tests/

# Sort imports
isort addon/*.py addon/tests/

# Check import sorting
isort --check-only addon/*.py addon/tests/

# Lint for critical errors (CI uses this)
flake8 addon/ addon/tests/ --count --select=E9,F63,F7,F82 --show-source --statistics

# Full linting check
flake8 addon/ addon/tests/ --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
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

# Build multi-architecture images (for release)
docker buildx build --platform linux/amd64,linux/arm64,linux/arm/v7 -t magiclight .
```

## Architecture

### Core Components
- `addon/main.py`: WebSocket client that connects to Home Assistant, handles authentication, subscribes to events, and processes ZHA switch button presses
- `addon/brain.py`: Adaptive lighting calculator that determines color temperature and brightness based on sun position and configurable curves
- `addon/light_controller.py`: Multi-protocol light controller with factory pattern for ZigBee, Z-Wave, WiFi, Matter
- `addon/switch.py`: Switch command processor handling button press events and light control
- `addon/webserver.py`: Web server for Light Designer interface accessible via Home Assistant ingress
- `addon/designer.html`: Interactive web UI for configuring adaptive lighting curves
- `addon/primitives.py`: Core service implementations for MagicLight operations

### Custom Integration Components
- `custom_components/magiclight/__init__.py`: Service registration and event forwarding
- `custom_components/magiclight/config_flow.py`: Configuration flow handling (minimal, service-only)
- `custom_components/magiclight/const.py`: Service names and constants
- `custom_components/magiclight/services.yaml`: Service definitions and parameters

### Key Architectural Patterns

#### Service-Only Integration Pattern
The custom integration doesn't manage state or entities - it only registers services that forward to WebSocket events:
1. Integration registers services with Home Assistant
2. Service calls are converted to WebSocket events
3. Add-on listens for these events and executes the actual logic
4. This avoids complexity of state management in the integration

#### WebSocket Event Flow
1. Custom integration service called → fires `magiclight_service_event`
2. Add-on subscribes to these events via WebSocket
3. Events contain service name and area parameter
4. Add-on executes appropriate primitive based on service

#### Multi-Protocol Light Control Factory
`light_controller.py` implements a factory pattern:
- Detects light protocol (ZHA, Z-Wave, WiFi, Matter)
- Returns appropriate control method for each light type
- Handles mixed-protocol areas gracefully
- Optimizes ZHA with group control when possible

### Configuration

#### Environment Variables (for local testing)
Create `addon/.env` file:
```
HA_HOST=localhost
HA_PORT=8123
HA_TOKEN=your_long_lived_token_here
HA_USE_SSL=false
```

#### Test Configuration
`addon/pytest.ini` configures:
- Test paths: `addon/tests/`
- Python path additions for imports
- Test discovery patterns

#### Build Configuration
`addon/build.yaml` defines:
- Multi-architecture support (amd64, armhf, armv7, aarch64)
- Build arguments and labels
- Container base images

### CI/CD Pipeline

GitHub Actions workflows (`.github/workflows/`):
- `build.yml`: Multi-arch Docker build validation
- `test.yml`: Pytest with coverage reporting
- `lint.yml`: Black formatting and flake8 linting
- `ci.yml`: Combined CI workflow

### Key Design Patterns

#### Event Processing Flow
1. WebSocket receives event (ZHA button or service call)
2. Device/area mapping resolved via registries
3. Sun position calculated from cached state
4. Adaptive values computed based on curves
5. Appropriate lights controlled via factory pattern

#### Adaptive Lighting Algorithm
- Solar time position (-1 to 1 scale)
- Separate morning/evening curves
- Configurable midpoint and steepness
- Step-based dimming along curve
- Color space conversions (Kelvin → RGB → XY)

#### ZHA Group Management
- Auto-creates/syncs groups with "Magic_" prefix
- Dedicated "Magic_Zigbee_Groups" area
- Smart method selection based on area composition
- Efficient group control for ZHA-only areas

#### Test Path Management
`addon/tests/conftest.py` injects parent directory into sys.path, allowing tests to import addon modules directly without package installation.

## Light Designer Interface
- Accessible at `/ingress_entry` when addon running
- API endpoints: `/api/config` (GET), `/api/save` (POST)
- Real-time preview of lighting curves
- Visual parameter controls with live updates
- Step markers for dimming visualization

## Service Primitives
- `magiclight_on`: Enable MagicLight mode and turn on with adaptive lighting
- `magiclight_off`: Disable MagicLight mode only (lights unchanged)
- `magiclight_toggle`: Smart toggle based on light state
- `step_up`/`step_down`: Adjust along adaptive curve
- `reset`: Reset to current time position

## Blueprint Automation
`blueprints/automation/magiclight/hue_dimmer_switch.yaml`:
- Multiple ZHA switch support
- Multiple area targeting
- Button mappings to service primitives

## Git Workflow
When creating commits:
1. Run tests: `pytest addon/tests/`
2. Check formatting: `black --check addon/*.py addon/tests/`
3. Lint: `flake8 addon/ addon/tests/ --select=E9,F63,F7,F82`
4. Update version in `addon/config.yaml` and `custom_components/magiclight/manifest.json`
5. Add entry to `addon/CHANGELOG.md`
6. Use conventional commit format

## Repository Notes
- Repository URLs need consolidation (multiple references exist)
- HACS installation via custom repository URL
- Docker Hub images published to `dtconceptsnc/magiclight`
- make sure to source .venv/bin/activate
- dont update the integration (custom_components) if no changes were made in there
