# Minimal Home Assistant

- Read ZigBee sensors using https://www.zigbee2mqtt.io/
- Store data to InfluxDB v1 
- Without HomeAssistant
- Run on a Raspberry


## Install
- Flash SD Card with RPI OS Lite
- 

## Install Zigbee2mqtt


```
chmod +x config/install_zigbee2mqtt.sh
./config/install_zigbee2mqtt.sh

sudo cp ./config/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/
sudo cp config/zigbee2mqtt/configuration.yaml /opt/zigbee2mqtt/data/
sudo cp config/systemd/zigbee2mqtt.service  /etc/systemd/system
sudo systemctl enable zigbee2mqtt.service 
sudo systemctl restart zigbee2mqtt.service 
sudo systemctl status zigbee2mqtt.service 
```

- Visit web app at http://$IP:8081/
- Look at messages use mqttui `mqttui -b mqtt://192.168.1.87`


## InfluxDB v1

see https://docs.influxdata.com/influxdb/v1/introduction/install/

and
```
sudo apt install influxdb-client
```

## Install

```
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
pip install -e .
```

```
...
sudo cp config/systemd/miniha_webapp.service /etc/systemd/system/
```

## Images
Temperatures and power usage daily graphs
![temps](images/temperature_2025-09-10.png)

![power](images/power_2025-09-10.png)
