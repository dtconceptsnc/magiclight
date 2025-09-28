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

### Step 3: Import the Blueprint (Recommended)

> The add-on automatically copies the Hue Dimmer blueprint into `/config/blueprints/automation/magiclight`. Use the button below if you prefer to import through the UI or run MagicLight without the add-on.

[![Import Blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdtconceptsnc%2Fmagiclight%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fmagiclight%2Fhue_dimmer_switch.yaml)

1. Click the button above to import the MagicLight Smart Switch Control blueprint
2. Or manually import from: **Settings** → **Automations & Scenes** → **Blueprints** → **Import Blueprint**
3. Use URL: `https://github.com/dtconceptsnc/magiclight/blob/main/blueprints/automation/magiclight/hue_dimmer_switch.yaml`
4. Create an automation from the blueprint:
   - Select your switch device(s) (supports ZHA and Hue Bridge)
   - Choose target area(s) to control
   - Save and activate the automation

The blueprint provides smart button mappings:
- **ON button**: Smart toggle (turns lights on with MagicLight or off)
- **OFF button**: Reset to current time and enable MagicLight
- **UP/DOWN buttons**: Step brightness along the adaptive curve

## 🚀 Quick Start

1. **Install the add-on and restart** following the steps above
2. **Create an automation** from the blueprint for your switch devices
3. **Press your configured switch** - lights in that area will automatically adjust
4. **Open Light Designer** from the Home Assistant sidebar to customize your preferences
5. **Enjoy** perfect lighting throughout the day!

## 📊 Light Designer

Access the Light Designer through your Home Assistant sidebar when the add-on is running. This intuitive interface lets you:

- Preview your lighting curves in real-time
- Adjust brightness and color temperature ranges
- Fine-tune morning and evening transitions
- Save configurations instantly

## 🔧 Compatibility

MagicLight works with:
- **Smart Switches**: ZHA-compatible switches (Hue, IKEA, Aqara, etc.)
- **Smart Lights**: ZigBee, Z-Wave, WiFi (Tuya, LIFX, etc.), Matter
- **Home Assistant**: 2023.1 or newer

## 📝 Configuration

MagicLight works out of the box with sensible defaults. For advanced users, customize through:

- **Add-on Configuration**: Adjust color modes and temperature ranges
- **Light Designer**: Visual interface for curve customization
- **YAML**: Advanced automation possibilities

## 🙏 Influences

- [Adaptive Lighting](https://github.com/basnijholt/adaptive-lighting)

## 👥 Contributors

- [@tkthundr](https://github.com/tkthundr)
- [@rweisbein](https://github.com/rweisbein)

## 📄 License

MagicLight is released under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.

---

**Need Help?** Open an [issue](https://github.com/dtconceptsnc/magiclight/issues) or check our [documentation](https://github.com/dtconceptsnc/magiclight/wiki).

**Love MagicLight?** Give us a ⭐ on GitHub!
