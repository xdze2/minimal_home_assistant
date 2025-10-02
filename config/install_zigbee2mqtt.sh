# !/bin/bash

# from https://www.zigbee2mqtt.io/guide/installation/01_linux.html#installing
# Set up Node.js repository, install Node.js and required dependencies.
# NOTE 1: Older i386 hardware can work with [unofficial-builds.nodejs.org](https://unofficial-builds.nodejs.org/download/release/v20.9.0/ e.g. Version 20.9.0 should work.
# NOTE 2: For Ubuntu see installing through Snap below.
sudo apt-get install -y curl mosquitto
sudo curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs git make g++ gcc libsystemd-dev
sudo corepack enable

# Verify that the correct Node.js version has been installed
node --version  # Should output V20.x, V22.X

# Create a directory for zigbee2mqtt and set your user as owner of it
sudo mkdir /opt/zigbee2mqtt
sudo chown -R ${USER}: /opt/zigbee2mqtt

# Clone Zigbee2MQTT repository
git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git /opt/zigbee2mqtt

# Install dependencies (as user "pi")
cd /opt/zigbee2mqtt
pnpm install --frozen-lockfile
