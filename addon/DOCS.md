# HomeGlo Add-on Documentation

## Configuration Options

### manage_integration
Automatically install and update the MagicLight custom integration inside Home Assistant.

### manage_blueprints
Ensure supported switches receive MagicLight Hue Dimmer automations in areas with lights.

## Designer Settings

The Light Designer UI (available via the add-on ingress panel) controls all lighting curve behaviour.
Use the **Color Output** section to choose how commands are sent to your lights:

- `kelvin` (default) – Sends color temperature values (most compatible across bulbs).
- `rgb` – Sends RGB color values.
- `xy` – Sends CIE xy coordinates.

The same interface also exposes brightness and color-temperature range sliders along with the
morning/evening curve parameters.

## How It Works

This add-on connects to Home Assistant's WebSocket API and listens for ZHA switch events. When a switch's top button is pressed, it automatically turns on lights in the corresponding area with adaptive lighting based on the sun's position.

The adaptive lighting adjusts both brightness and color temperature throughout the day to provide natural, comfortable lighting.
