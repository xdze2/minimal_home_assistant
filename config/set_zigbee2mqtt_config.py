from miniha.config_edit import edit_yaml

CONFIG_PATH = "/opt/zigbee2mqtt/data/configuration.yaml"

# Set mqtt.include_device_information to true
edit_yaml(CONFIG_PATH, "mqtt.include_device_information", True)

# Set advanced.last_seen to ISO_8601
edit_yaml(CONFIG_PATH, "advanced.last_seen", "ISO_8601")
