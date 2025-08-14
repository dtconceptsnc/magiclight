#!/bin/bash
# Script to test the Python app locally

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and configure your settings."
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check if token is set
if [ -z "$HA_TOKEN" ] || [ "$HA_TOKEN" = "your_long_lived_access_token_here" ]; then
    echo "Error: HA_TOKEN not configured!"
    echo "Please update your .env file with a valid Home Assistant token."
    exit 1
fi

# Install dependencies if needed
if ! python3 -c "import websockets" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Run the app
echo "Starting Home Assistant WebSocket listener..."
echo "Connecting to $HA_HOST:$HA_PORT"
python3 main.py