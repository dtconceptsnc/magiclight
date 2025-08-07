<!-- https://developers.home-assistant.io/docs/add-ons/presentation#keeping-a-changelog -->

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