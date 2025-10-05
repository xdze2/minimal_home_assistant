from miniha.config_edit import edit_yaml

CONFIG_PATH = "/opt/zigbee2mqtt/data/configuration.yaml"

# Set mqtt.include_device_information to true
edit_yaml(CONFIG_PATH, "mqtt.include_device_information", True)

# Set advanced.last_seen to ISO_8601
edit_yaml(CONFIG_PATH, "advanced.last_seen", "ISO_8601")


# Set device friendly names
edit_yaml(CONFIG_PATH, "devices.0x00124b00291976e0.friendly_name", "sensors/thB")
edit_yaml(CONFIG_PATH, "devices.0x00124b00291976e9.friendly_name", "sensors/thA")
edit_yaml(CONFIG_PATH, "devices.0x00124b0029193cea.friendly_name", "sensors/thC")
edit_yaml(CONFIG_PATH, "devices.0x00124b002919774f.friendly_name", "sensors/thE")


edit_yaml(CONFIG_PATH, "devices.0x00158d0005d29e40.friendly_name", "linky")
