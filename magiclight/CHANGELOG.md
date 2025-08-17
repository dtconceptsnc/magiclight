<!-- https://developers.home-assistant.io/docs/add-ons/presentation#keeping-a-changelog -->

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