# Intuitive Light Add-on Documentation

## Configuration Options

### color_mode
Specifies how the add-on sends color information to lights. Options:
- `kelvin` (default) - Uses color temperature in Kelvin. Most compatible with various bulb types.
- `rgb` - Uses RGB color values
- `xy` - Uses CIE xy color coordinates

### min_color_temp
Minimum color temperature in Kelvin (warmest/most orange). Default: 500K

### max_color_temp  
Maximum color temperature in Kelvin (coolest/most blue). Default: 6500K

## How It Works

This add-on connects to Home Assistant's WebSocket API and listens for ZHA switch events. When a switch's top button is pressed, it automatically turns on lights in the corresponding area with adaptive lighting based on the sun's position.

The adaptive lighting adjusts both brightness and color temperature throughout the day to provide natural, comfortable lighting.