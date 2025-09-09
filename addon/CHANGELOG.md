<!-- https://developers.home-assistant.io/docs/add-ons/presentation#keeping-a-changelog -->

## 2.5.1

- Changed default color mode to Kelvin (CT) for better bulb compatibility
  - Most bulbs support color temperature (CT) mode
  - Previous default was XY which some bulbs don't support well
  - Updated configuration defaults and documentation

## 2.5.0

- Simplified brightness stepping algorithm
  - Replaced complex arc-based perceptual stepping with straightforward percentage-based approach
  - Step size now calculated as (max_brightness - min_brightness) / steps
  - Removed gamma/perceptual brightness adjustments for more predictable behavior
  - Python implementation now matches JavaScript designer exactly
  - Stepping behavior is now linear and intuitive

- Designer interface improvements
  - Added "Show steps" checkbox to visualize step markers on the graph
  - Step markers show where each button press will land with proper color coding
  - Enhanced click precision using correct plot area detection
  - Fixed graph rendering issues
  - Removed "Prioritize dim steps" control (no longer needed with simplified algorithm)

- Code simplification
  - Removed perceptual weight constants and calculations
  - Eliminated complex arc distance computations
  - Cleaner, more maintainable codebase
  - Better alignment between Python and JavaScript implementations

## 2.4.0

- New simplified adaptive lighting algorithm
  - Replaced complex logistic curves with simplified midpoint/steepness parameters
  - Removed gain/offset/decay parameters for cleaner configuration
  - Added arc-based stepping for perceptually uniform dim/brighten transitions
  - Added gamma-based brightness perception (controlled via "Prioritize dim steps" slider)
  - Smoother and more predictable lighting transitions

- Designer improvements
  - Save Configuration button moved to top for better visibility
  - Added "Prioritize dim steps" control for customizing step behavior
  - Visual hash marks on sliders showing default values
  - Location parameters (lat/lon/timezone) now display-only from Home Assistant
  - Test month selector no longer saved (always defaults to current month)
  - Sun power curve visually dimmed for better contrast
  - Fixed midpoint labels to refresh when sun position changes

- Testing improvements
  - Added comprehensive pytest test suite
  - Tests organized in tests/unit/ directory
  - Added TESTING.md documentation
  - Fixed async test issues

## 2.3.5

- Startup optimization
  - Eliminated redundant device registry loading during startup
  - Reduced state queries from 3 to 2 during initialization  
  - Areas data is now shared between sync and parity cache operations
  - Added `refresh_devices` parameter to control when device registry is reloaded
  - Faster startup with less duplicate work

## 2.3.4

- Performance improvements
  - Fixed duplicate ZHA group synchronization on startup
  - Removed redundant parity cache refresh calls in event handlers
  - Consolidated sync flow to prevent multiple unnecessary operations
  - Added clearer logging with separators for sync operations

- Area naming update
  - Changed dedicated area name from "Glo" to "Glo_Zigbee_Groups" for clarity
  - Better identifies the purpose of the organizational area

## 2.3.3

- ZHA group organization improvements
  - Automatically creates a "Glo_Zigbee_Groups" area to organize all ZHA group entities
  - Moves ZHA group entities to Glo_Zigbee_Groups area after creation to prevent random placement
  - Moves existing group entities to Glo_Zigbee_Groups area during sync
  - Excludes Glo_Zigbee_Groups area from parity checks and light control operations
  - Prevents Home Assistant from placing groups in random areas

- Better group entity management
  - Finds and moves group entities using entity registry
  - Ensures consistent organization of all Glo_ prefixed groups
  - Properly updates entity area assignments after group creation

## 2.3.2

- Fixed WebSocket concurrency issues
  - Added area parity caching to prevent concurrent WebSocket calls during light control
  - Cache is refreshed during initialization and when areas/devices change
  - Eliminates "cannot call recv while another coroutine is already waiting" errors

- Consolidated light control logic
  - Single `determine_light_target` method decides between ZHA group or area control
  - All light operations now use the same consistent logic
  - Removed duplicate code across switch operations

- Improved code structure
  - Simplified switch.py by removing unused light controller code
  - All light control now goes through unified service calls
  - Better separation of concerns between parity checking and light control

## 2.3.1

- Smart light control method selection
  - Added ZHA parity checking to determine optimal control method per area
  - Areas with only ZHA lights use efficient ZHA group control
  - Areas with mixed light types (ZHA + WiFi/Matter/etc) use area-based control
  - Automatically selects best method to ensure all lights are controlled
  - Enhanced logging to show which control method is used and why

- Improved light compatibility
  - Better support for mixed-protocol rooms (ZHA, WiFi, Matter, Z-Wave, etc)
  - ZHA groups only created for areas with 100% ZHA lights
  - Non-ZHA light detection and tracking for proper control method selection

## 2.3.0

- Adaptive lighting dimming improvements
  - Fixed dimming buttons to respect min/max color temperature boundaries
  - Fixed dimming buttons to respect min/max brightness boundaries
  - Added support for configurable min/max values via environment variables
  - Dimming step calculations now properly use user-configured limits

- Time offset persistence
  - Time offsets are now saved when lights are turned off
  - Saved offsets are automatically restored when lights are turned on
  - Offsets persist across addon restarts
  - Each room maintains its own independent time offset preference

- Code improvements
  - Removed flash functionality from disable_magic_mode
  - Consolidated data directory handling into single method
  - Improved offset management for better user experience

## 2.2.2

- Auto-sync ZHA groups when devices change areas
  - Added event listeners for device_registry_updated events
  - Added event listeners for area_registry_updated events  
  - Added event listeners for entity_registry_updated events
  - Automatically resync ZHA groups when devices are added, removed, or moved between areas
  - Fixed bug where existing group members were not properly detected (nested device structure)
  - Enhanced logging to show group membership changes during sync
  - Groups now properly remove devices when they're moved to different areas

## 2.2.1

- Fixed initialization and ZHA group mapping
  - Fixed latitude/longitude data not loading (now properly waits for config response)
  - Fixed ZHA group discovery (now loads states before device registry)
  - Improved ZHA group to area mapping with multiple name variations
  - Added random 16-bit group ID generation for new ZHA groups
  - Enhanced logging for debugging group and location loading
  - Removed duplicated ZHA group mapping code

- Code refactoring
  - Centralized ZHA group mapping logic into single method
  - Converted async fire-and-forget methods to proper await patterns
  - Added comprehensive debug logging with ✓/⚠ status indicators

## 2.2.0

- Major refactor: Multi-protocol light controller architecture
  - Created modular light_controller.py with protocol abstraction layer
  - Support for multiple lighting protocols (ZigBee, Z-Wave, WiFi, Matter, HomeAssistant)
  - Protocol-agnostic LightCommand interface for unified light control
  - Automatic protocol detection based on device type
  - Future-ready architecture for mixed-protocol environments

- ZHA group synchronization with Home Assistant areas
  - Automatically creates/updates ZHA groups to match HA areas on startup
  - Groups named with "Glo_" prefix to avoid conflicts with other integrations
  - Only creates groups for areas that have switches installed
  - Syncs group membership when lights are added/removed from areas
  - Removes obsolete groups when areas are deleted
  - Improved device discovery using device registry identifiers
  - Enhanced IEEE address extraction from HA device identifiers
  - Better endpoint detection for different light types (Hue uses endpoint 11)

- Enhanced debugging and logging
  - Detailed logging for ZHA device discovery and group operations
  - IEEE address and endpoint information logged for troubleshooting
  - Group synchronization status reporting

- Fixed WebSocket API implementation
  - Corrected service call parameter structure for light control
  - Added send_message_wait_response for synchronous WebSocket operations
  - Improved error handling for WebSocket messages

- Switch handling improvements
  - Abstracted switch operations to use light controller
  - Protocol-aware switch commands
  - Better separation of switch logic from light implementation

## 2.1.11

- Fix dimming to use saved designer curve parameters
  - Fixed critical issue where dimming used default curves while main lighting used saved curves
  - Dimming now properly uses the same curve parameters as configured in Light Designer
  - Eliminates brightness jumps caused by curve parameter mismatch
- Enable designer configuration saving in development environment
  - Development mode now uses .data/ directory for configuration persistence
  - Designer settings can now be saved and tested locally

## 2.1.10

- Fix dimming calculation to prevent large brightness jumps
  - Fixed issue where dimming could jump from 90% to 4% brightness
  - Brightness now correctly follows the adaptive curve without interpolation artifacts
  - Recalculates actual curve values instead of interpolating between samples

## 2.1.9

- Bottom button behavior changes
  - Bottom button now always resets to time offset 0 and enables magic mode
  - Removed toggle behavior - bottom button consistently returns to present time
  - Dim up button no longer turns on lights when they're off

## 2.1.8

- Fix Light Designer configuration persistence again

## 2.1.7

- Fix Light Designer configuration persistence
  - Designer now properly loads all configuration values
  - MAX_DIM_STEPS value correctly synchronized between Python and web interface
  - Configuration reliably persists across container restarts and updates
  - Improved error handling when loading saved configuration
  - Move Save Configuration button below chart, above controls

## 2.1.6

- Add adaptive / step arc support + update designer
  - Dimmer switches now adjust brightness along the new step arc
  - Light Designer updated to visualize and test dimming behavior with offset controls
  - Shows real-time preview of how dimming affects lighting values

## 2.0.5

- Auto-reset manual offsets at solar midnight
  - Manual adjustments from dimmer switches now automatically reset to 0 at solar midnight
  - Ensures lighting curves start fresh each day without accumulated offsets
  - Reset happens seamlessly in background during periodic updates
  - Lights in magic mode will update to correct values when offsets reset

## 2.0.4

- Simplify Light Designer interface
  - Removed latitude, longitude, and timezone controls (automatically provided by Home Assistant)
  - Renamed "Sun Position" section to "Display Settings"
  - Added informational note about automatic location detection
  - Kept month selector for testing seasonal variations
  - Cleaner, more focused interface for curve configuration

## 2.0.3

- Improve Light Designer configuration handling and feedback
  - Designer now fetches current configuration via API on page load
  - Added cache-control headers to prevent browser caching issues
  - Enhanced save confirmation with clearer visual feedback
  - Save button shows loading state during save operation
  - Success/error messages are more prominent with animations
  - Configuration always shows the most recent saved values

## 2.0.2

- Fix API routing for POST requests in Light Designer
  - Fixed 405 Method Not Allowed errors when saving configuration
  - Added proper route handlers for ingress-prefixed API paths
  - Routes now correctly handle both GET and POST methods with ingress prefixes
  - Configuration changes apply in real-time without addon restart

## 2.0.1

- Fix ingress routing for Light Designer interface
  - Fixed 404 errors when accessing through Home Assistant sidebar
  - Added catch-all route to handle ingress path prefixes
  - Updated API routes to work with relative paths
  - Reordered route registration to ensure API endpoints work correctly

## 2.0.0

- Add Home Assistant ingress support with Light Designer interface
  - New web-based Light Designer accessible through Home Assistant sidebar
  - Interactive graph showing real-time preview of lighting curves
  - Visual controls for all 20 curve parameters with live updates
  - Separate morning and evening controls for brightness and color temperature
  - Save configuration directly from the web interface
  - Visualizes solar events (sunrise, sunset, solar noon, solar midnight)
  - Shows current time marker and interactive time selection
  - Drag-to-select time on graph for instant value preview

## 1.4.0

- Replace cubic smoothstep formula with advanced morning/evening curves
  - Replaced simple gamma-based cubic formula with separate morning and evening logistic curves
  - Added 20 new curve parameters for fine-grained control over lighting transitions
  - Morning curves control lighting from solar midnight to solar noon
  - Evening curves control lighting from solar noon to solar midnight
  - Each curve has independent controls for midpoint, steepness, decay, gain, and offset
  - Allows for asymmetric lighting patterns (e.g., slower sunrise, faster sunset)
  - Better matches natural circadian rhythms with customizable transitions
  - Removed deprecated sun_cct_gamma and sun_brightness_gamma parameters

## 1.3.6

- Fix multi-area switch control bug
  - Magic mode is no longer automatically enabled at startup for all areas
  - Magic mode is now properly managed per-area based on light state
  - Fixes issue where switches in one area could interfere with other areas
  - Each area now maintains independent magic mode state

## 1.3.5

- Version skipped

## 1.3.4

- Improved color temperature conversion accuracy
  - Rewrote color_temperature_to_rgb using Krystek polynomial approach
  - Now converts CCT → xy → XYZ → RGB for better accuracy
  - Added proper sRGB gamma correction
  - Enhanced color_temperature_to_xy with more precise coefficients
  - Added separate polynomial ranges for improved accuracy (2222K and 4000K breakpoints)

## 1.3.3

- Fix sun position calculation to match expected behavior
  - Changed from sun elevation angle to time-based cosine wave
  - Now uses local solar time for proper solar noon alignment
  - Provides smooth -1 to +1 progression over 24 hours
  - Matches the HTML visualization formula exactly

## 1.3.2

- Fix gamma parameters not being passed from addon configuration
  - Added sun_cct_gamma and sun_brightness_gamma to run script
  - Now properly exports configuration values as environment variables
  - Gamma parameters will correctly affect adaptive lighting curves

## 1.3.1

- Add configurable gamma parameters for adaptive lighting curves
  - New sun_cct_gamma parameter to control color temperature curve (default: 0.9)
  - New sun_brightness_gamma parameter to control brightness curve (default: 0.5)
  - Allows fine-tuning of how lighting changes throughout the day
  - Lower gamma values = warmer/dimmer during day, higher = cooler/brighter

## 1.3.0

- Add configurable color mode support
  - New dropdown configuration to choose between kelvin, rgb, or xy color modes
  - Direct color temperature to CIE xy conversion without RGB intermediate step
  - Centralized light control function for consistent color handling
  - Default color mode changed to RGB for wider device compatibility
- Add configurable color temperature range
  - Min and max color temperature now adjustable in addon configuration
  - Allows customization for different lighting preferences and hardware
  - Default range: 500K (warm) to 6500K (cool)
- Remove lux sensor adjustment feature
  - Simplified configuration by removing lux_adjustment option
  - Cleaner codebase focused on core adaptive lighting functionality

## 1.2.9

- Add support for ZHA group light entities
  - Automatically detects and uses ZHA group entities (Light_AREA pattern)
  - Searches both entity_id and friendly_name for Light_ pattern
  - Uses single ZHA group entity instead of controlling individual lights
  - Improved logging to show all discovered light entities for debugging

## 1.2.8

  - Triple press OFF random RGB!

## 1.2.7

- Enhanced magic mode dimming behavior
  - Dim up/down buttons now move along the adaptive lighting curve when in magic mode
  - Before solar noon: dim up moves forward in time (brighter), dim down moves backward (dimmer)
  - After solar noon: dim up moves backward in time (brighter), dim down moves forward (dimmer)
  - Bottom button now toggles magic mode: turns it off with flash if on, or enables it with adaptive lighting if lights are on
  - Brightness adjustments never turn lights off, maintaining minimum 1% brightness

## 1.2.6

- Implement global magic mode management
  - Magic mode is now enabled by default on startup for all areas with switches
  - Top button press toggles lights and enables/disables magic mode
  - Bottom button press disengages magic mode without turning lights off
  - Visual flash indication when magic mode is disabled
  - Centralized magic mode disable function with consistent behavior

## 1.2.5

- Version skipped

## 1.2.4

- Add configuration toggle for lux adjustment
  - New "Lux adjustment" checkbox in Home Assistant configuration tab
  - When enabled, applies lux-based brightness and color temperature adjustments
  - Disabled by default for backward compatibility
  - Lux adjustment remains optional and only applies when lux sensors are available

## 1.2.3

- Add lux sensor support for adaptive lighting
  - Automatically detects and uses lux sensors (area-specific or general)
  - Lux adjustments applied as post-processing stage for better modularity
  - Bright environments shift toward cooler colors and reduced brightness
  - Dark environments maintain warmer colors and appropriate brightness
  - Configurable lux boundaries and adjustment weights

## 1.2.2

- Remove sleep mode functionality from adaptive lighting
- Fix color temperature to continue fading through negative sun positions
- Simplify lighting formula for smoother transitions throughout day/night cycle

## 1.2.1

- Fix magic mode not being disabled when using ON button to toggle lights off
- Ensure magic mode is only active when lights are on

## 1.2.0

- Add "Magic Mode" feature for automatic adaptive lighting updates
  - Areas enter magic mode when lights are turned on via switch
  - Areas exit magic mode when lights are turned off via switch
  - Background task only updates lights in areas that are in magic mode
- Add support for off button press to turn off lights and disable magic mode
- Remove requirement for all lights to be on before background updates
- Improve logging for magic mode state changes

## 1.0.0

- Initial release