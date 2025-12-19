# MagicLight - Adaptive Lighting for Home Assistant

![MagicLight Light Designer](.github/assets/designer.png)

Transform your home's ambiance with MagicLight, the intelligent lighting system that automatically adjusts your lights throughout the day to match natural sunlight patterns.

## ✨ Features

- **Smart Switch Automation** - Provided blueprint sets up Hue Dimmer Switch functionality in minutes
- **Visual Light Designer** - Interactive web interface to perfect your lighting curves
- **Magic Mode** - Automatically updates lights every minute to follow curve

## 📦 Installation

> **⚠️ IMPORTANT**: Install the MagicLight Home Assistant add-on and then restart Home Assistant. The add-on includes the adaptive lighting engine, Light Designer, services, and blueprints—no separate integration required.

### Step 1: Install the Home Assistant Add-on

[![Add MagicLight Repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fdtconceptsnc%2Fmagiclight)

1. Click the button above to add the MagicLight repository to your Home Assistant
2. Navigate to **Settings** → **Add-ons** → **Add-on Store**
3. Find "MagicLight" and click Install
4. Start the add-on and check the logs

### Step 2: Restart Home Assistant

1. Restart from **Settings** → **System** → **Restart** (or use the power menu)
2. Wait for Home Assistant to come back online; MagicLight services will be ready

## 🚀 Quick Start

1. **Install the add-on and restart** following the steps above
2. **Create an automation** from the automatically-installed blueprint
3. **Press your configured switch** - lights in that area will automatically adjust
4. **Enjoy** perfect lighting throughout the day!

The blueprint provides smart button mappings:
- **ON button**: Smart toggle (turns lights on with MagicLight or off)
- **OFF button**: Reset to current time and enable MagicLight
- **UP/DOWN buttons**: Step brightness along the adaptive curve

## 🛠️ Service Primitives

MagicLight registers a set of service primitives under the `magiclight` domain. These are the same calls the add-on and blueprints use, so you can trigger them from automations, scripts, dashboards, or the Developer Tools. Every service accepts an `area_id` field that can be a single area or a list for grouped control.

- `magiclight.step_up` – Moves the area forward along the MagicLight curve, brightening and cooling the lights by advancing the stored TimeLocation offset.
- `magiclight.step_down` – Moves backward along the curve, dimming and warming the lights by reducing the TimeLocation offset.
- `magiclight.dim_up` – Raises brightness while keeping the current color temperature; in MagicLight mode it adjusts the brightness offset, otherwise it issues a standard Home Assistant brightness step.
- `magiclight.dim_down` – Lowers brightness without touching color temperature, following the same MagicLight-aware logic as `dim_up`.
- `magiclight.reset` – Clears any offsets, re-enables MagicLight, and reapplies the lighting that matches the current time.
- `magiclight.magiclight_on` – Enables MagicLight for the area and turns lights on with the adaptive values for the active curve position.
- `magiclight.magiclight_off` – Disables MagicLight but leaves the lights exactly as they are, saving the current TimeLocation for later.
- `magiclight.magiclight_toggle` – Smart toggle: if any lights in the target areas are on it turns everything off and disables MagicLight; otherwise it turns them on with MagicLight active.

## 🙏 Influences

- [Adaptive Lighting](https://github.com/basnijholt/adaptive-lighting)

## 👥 Contributors

- [@tkthundr](https://github.com/tkthundr)
- [@rweisbein](https://github.com/rweisbein)

## 📄 License

MagicLight is released under the MIT License. See [LICENSE](LICENSE) for details.

---

**Need Help?** Join our [Discord community](https://discord.gg/TUvSrtRt), open an [issue](https://github.com/dtconceptsnc/magiclight/issues), or check our [documentation](https://github.com/dtconceptsnc/magiclight/wiki).

**Love MagicLight?** Give us a ⭐ on GitHub!
