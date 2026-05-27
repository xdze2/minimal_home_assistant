# Minimal Home Assistant

- Read ZigBee sensors using https://www.zigbee2mqtt.io/
- Store data to InfluxDB v1
- Without HomeAssistant
- Run on a Raspberry

## Install

- Flash SD Card with RPI OS Lite 64-bit (with Pi Imager)

## Allow UART console

https://raspberrypi.stackexchange.com/a/108781

- add `enable_uart=1` to `bootfs/config.txt`
- add `console=tty1` to `bootfs/cmdline.txt` (already done)

use `sudo minicom -D /dev/ttyUSB0`

## Install Zigbee2mqtt

install: https://www.zigbee2mqtt.io/guide/installation/01_linux.html

```
chmod +x config/install_zigbee2mqtt.sh
./config/install_zigbee2mqtt.sh

sudo cp ./config/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/


# ~sudo cp config/zigbee2mqtt/configuration.yaml /opt/zigbee2mqtt/data/~

sudo chown bird:bird /opt/zigbee2mqtt/data/configuration.yaml

# Do config by hand (web assistant)
python3 config/set_zigbee2mqtt_config.py
sudo cp config/systemd/zigbee2mqtt.service  /etc/systemd/system
sudo systemctl enable zigbee2mqtt.service
sudo systemctl restart zigbee2mqtt.service
sudo systemctl status zigbee2mqtt.service
```

- Visit web app at http://$IP:8081/
- Look at messages use mqttui `mqttui -b mqtt://192.168.1.87`

to fix systemd notify:

- https://github.com/Koenkk/zigbee2mqtt/issues/26946#issuecomment-3185029961
- plus `sudo apt install linux-libc-dev-arm64-cross`

## InfluxDB v1

see https://docs.influxdata.com/influxdb/v1/introduction/install/

and

```
# add repo...
sudo apt install influxdb-client
```

Set data dir to external drive:

```
mkdir /media/data/influxdb
sudo chown influxdb:influxdb /media/data/influxdb
sudo cp /etc/influxdb/influxdb.conf /etc/influxdb/influxdb.conf.bck
sudo cp config/influxdb/influxdb.conf /etc/influxdb/influxdb.conf
sudo mkdir /etc/systemd/system/influxdb.service.d
sudo cp config/systemd/override.conf /etc/systemd/system/influxdb.service.d/
sudo service influxdb restart
```

## MiniHa services

```
sudo apt install git
sudo apt install python3-dev
sudo apt install mosquitto
```

```
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
pip install -e .
```

```
sudo cp config/systemd/miniha_webapp.service /etc/systemd/system/
sudo cp config/systemd/mqtt_to_influx.service /etc/systemd/system/
sudo cp config/systemd/daikin_to_influx.service /etc/systemd/system/
sudo systemctl enable miniha_webapp.service
sudo systemctl enable mqtt_to_influx.service
sudo systemctl enable daikin_to_influx.service
```

- Visit: http://192.168.1.87:5000/

## Influx1 client

## Images

Temperatures and power usage daily graphs
![temps](images/temperature_2025-09-10.png)

![power](images/power_2025-09-10.png)
