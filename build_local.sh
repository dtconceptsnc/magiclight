#!/bin/bash

# Quick build script for local testing from repository root
# Builds for current architecture without cache

set -e

# Resolve important paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}"
ADDON_DIR="${REPO_ROOT}/addon"

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
            echo "  -h, --help          Display this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use -h for help"
            exit 1
            ;;
    esac
done

# Ensure addon directory exists
if [[ ! -d "${ADDON_DIR}" ]]; then
    echo "Error: addon directory not found at ${ADDON_DIR}"
    exit 1
fi

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
echo "Using repository root as Docker build context: ${REPO_ROOT}"

docker run --rm -it --name builder --privileged \
    -v "${REPO_ROOT}":/data \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    ghcr.io/home-assistant/amd64-builder \
    -t /data/addon \
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

    # Determine if .env file exists at repo root
    if [ -f "${REPO_ROOT}/.env" ]; then
        ENV_FILE="--env-file ${REPO_ROOT}/.env"
        echo "Using ${REPO_ROOT}/.env for configuration"
    else
        echo "Warning: No .env file found at ${REPO_ROOT}/.env. Using environment variables."
        ENV_FILE=""

        # Check if HA_TOKEN is set
        if [ -z "${HA_TOKEN}" ]; then
            echo ""
            echo "ERROR: HA_TOKEN environment variable is not set!"
            echo ""
            echo "Please either:"
            echo "1. Create ${REPO_ROOT}/.env with HA_TOKEN=your_token_here"
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
