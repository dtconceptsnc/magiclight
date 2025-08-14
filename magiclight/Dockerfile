# https://developers.home-assistant.io/docs/add-ons/configuration#add-on-dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

# Execute during the build of the image
ARG TEMPIO_VERSION BUILD_ARCH
RUN \
    curl -sSLf -o /usr/bin/tempio \
    "https://github.com/home-assistant/tempio/releases/download/${TEMPIO_VERSION}/tempio_${BUILD_ARCH}"

# Install Python and dependencies
RUN apk add --no-cache python3 py3-pip tzdata

# Copy Python app
WORKDIR /app
COPY main.py brain.py switch.py requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy root filesystem
COPY rootfs /
