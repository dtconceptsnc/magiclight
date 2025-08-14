#!/bin/bash

# Build script for MagicLight Home Assistant addon
# Supports multiple architectures

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
ARCH=""
TEST_MODE=""
NO_CACHE=""
PUSH_MODE=""

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo "Options:"
    echo "  -a, --arch ARCH      Build for specific architecture (amd64, aarch64, armv7, armhf, i386)"
    echo "  -t, --test           Run in test mode"
    echo "  -n, --no-cache       Build without cache"
    echo "  -p, --push           Push to registry after build"
    echo "  --all                Build for all architectures"
    echo "  -h, --help           Display this help message"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--arch)
            ARCH="$2"
            shift 2
            ;;
        -t|--test)
            TEST_MODE="--test"
            shift
            ;;
        -n|--no-cache)
            NO_CACHE="--no-cache"
            shift
            ;;
        -p|--push)
            PUSH_MODE="--push"
            shift
            ;;
        --all)
            ARCH="all"
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Check if architecture is specified
if [ -z "$ARCH" ]; then
    echo -e "${YELLOW}No architecture specified. Building for current architecture...${NC}"
    # Detect current architecture
    case $(uname -m) in
        x86_64)
            ARCH="amd64"
            ;;
        aarch64)
            ARCH="aarch64"
            ;;
        armv7l)
            ARCH="armv7"
            ;;
        *)
            echo -e "${RED}Unable to detect architecture. Please specify with -a option.${NC}"
            exit 1
            ;;
    esac
fi

# Function to build for a single architecture
build_arch() {
    local arch=$1
    echo -e "${GREEN}Building MagicLight addon for ${arch}...${NC}"
    
    docker run --rm -it --name builder --privileged \
        -v "$(pwd)/magiclight":/data \
        -v /var/run/docker.sock:/var/run/docker.sock:ro \
        ghcr.io/home-assistant/amd64-builder \
        -t /data \
        ${TEST_MODE} \
        --${arch} \
        -i magiclight-${arch} \
        -d local \
        ${NO_CACHE} \
        ${PUSH_MODE}
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Successfully built for ${arch}${NC}"
    else
        echo -e "${RED}Failed to build for ${arch}${NC}"
        exit 1
    fi
}

# Main build process
cd "$(dirname "$0")"

echo -e "${GREEN}MagicLight Home Assistant Addon Builder${NC}"
echo "======================================"

# Validate addon configuration
if [ ! -f "magiclight/config.yaml" ]; then
    echo -e "${RED}Error: config.yaml not found in magiclight directory${NC}"
    exit 1
fi

# Build based on architecture selection
if [ "$ARCH" == "all" ]; then
    echo -e "${YELLOW}Building for all architectures...${NC}"
    for arch in amd64 aarch64 armv7 armhf i386; do
        build_arch $arch
    done
else
    build_arch $ARCH
fi

echo -e "${GREEN}Build complete!${NC}"

# Display next steps
if [ -z "$PUSH_MODE" ]; then
    echo ""
    echo "To test the addon locally:"
    echo "  1. The image is available as: magiclight-${ARCH}:latest"
    echo "  2. You can install it through the Home Assistant UI"
    echo ""
    echo "To push to a registry, run with --push option"
fi