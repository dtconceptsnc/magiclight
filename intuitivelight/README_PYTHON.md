# Home Assistant WebSocket Client

This Python application connects to Home Assistant's WebSocket API and listens for events.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Configure connection:
   - Copy `.env.example` to `.env`
   - Update with your Home Assistant details:
     - `HA_HOST`: Your Home Assistant host (default: localhost)
     - `HA_PORT`: Your Home Assistant port (default: 8123)
     - `HA_TOKEN`: Your long-lived access token (required)
     - `HA_USE_SSL`: Whether to use SSL (default: false)

   To get a long-lived access token:
   1. Go to your Home Assistant profile
   2. Scroll to "Long-Lived Access Tokens"
   3. Create a new token

3. Run locally:
   ```bash
   python main.py
   ```

## Features

- Connects to Home Assistant WebSocket API
- Authenticates using long-lived access token
- Subscribes to all events by default
- Logs state changes and other events
- Automatic reconnection on connection loss

## Environment Variables

- `HA_HOST`: Home Assistant host
- `HA_PORT`: Home Assistant port
- `HA_TOKEN`: Long-lived access token (required)
- `HA_USE_SSL`: Use SSL/TLS connection (true/false)