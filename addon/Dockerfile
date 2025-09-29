# https://developers.home-assistant.io/docs/add-ons/configuration#add-on-dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

# Execute during the build of the image
ARG TEMPIO_VERSION BUILD_ARCH
RUN \
    curl -sSLf -o /usr/bin/tempio \
    "https://github.com/home-assistant/tempio/releases/download/${TEMPIO_VERSION}/tempio_${BUILD_ARCH}"

# Install Python and dependencies
# py3-aiohttp provides pre-built aiohttp package - much faster!
RUN apk add --no-cache python3 py3-pip py3-aiohttp py3-aiofiles tzdata curl

# Copy Python app
WORKDIR /app
COPY *.py *.html requirements.txt ./

# Install only the packages not available from Alpine repos
RUN pip3 install --no-cache-dir websockets==12.0 python-dateutil==2.8.2 astral==3.2 PyYAML==6.0.1

# Copy root filesystem
COPY rootfs /
