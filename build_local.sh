#!/bin/bash

# Quick build script for local testing
# Builds for current architecture without cache

set -e

# Default values
RUN_AFTER_BUILD=false
HOST_PORT=8099

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--run)
            RUN_AFTER_BUILD=true
            shift
            ;;
        -p|--port)
            if [[ -n $2 && $2 != -* ]]; then
                HOST_PORT="$2"
                shift 2
            else
                echo "Error: --port requires a value (e.g. --port 8099)"
                exit 1
            fi
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -r, --run           Run the container after building"
            echo "  -p, --port <port>   Host port to map to 8099 (default: 8099)"
            echo "  -h, --help   Display this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h for help"
            exit 1
            ;;
    esac
done

# Detect current architecture
case $(uname -m) in
    x86_64)
        ARCH="amd64"
        ;;
    aarch64|arm64)
        ARCH="aarch64"
        ;;
    armv7l)
        ARCH="armv7"
        ;;
    *)
        echo "Unsupported architecture: $(uname -m)"
        exit 1
        ;;
esac

echo "Building MagicLight addon for $ARCH (no cache)..."

docker run --rm -it --name builder --privileged \
    -v "$(pwd)/magiclight":/data \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    ghcr.io/home-assistant/amd64-builder \
    -t /data \
    --test \
    --${ARCH} \
    -i magiclight-${ARCH} \
    -d local \
    --no-cache

echo "Build complete! Image: local/magiclight-${ARCH}:latest"

# Run the container if requested
if [ "$RUN_AFTER_BUILD" = true ]; then
    echo ""
    echo "Running MagicLight container..."
    echo "Press Ctrl+C to stop"
    echo ""
    
    # Check if .env file exists
    if [ -f "magiclight/.env" ]; then
        ENV_FILE="--env-file magiclight/.env"
        echo "Using .env file for configuration"
    else
        echo "Warning: No .env file found. Using environment variables."
        ENV_FILE=""
        
        # Check if HA_TOKEN is set
        if [ -z "${HA_TOKEN}" ]; then
            echo ""
            echo "ERROR: HA_TOKEN environment variable is not set!"
            echo ""
            echo "Please either:"
            echo "1. Create magiclight/.env file with HA_TOKEN=your_token_here"
            echo "2. Or set environment variable: export HA_TOKEN='your_token_here'"
            echo ""
            exit 1
        fi
    fi
    
    # The builder creates images with 'local/' prefix
    docker run --rm -it \
        --name magiclight-test \
        ${ENV_FILE} \
        -p "${HOST_PORT}:8099" \
        local/magiclight-${ARCH}:latest
    
    echo ""
    echo "Light Designer web UI should be available at: http://localhost:${HOST_PORT}"
fi
