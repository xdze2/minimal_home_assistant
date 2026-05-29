from daikinapi import Daikin
import requests

from miniha.devices import load_devices

devices = load_devices().daikin
ip_address = devices[-1].ip
print(f"Connecting to Daikin AC at {ip_address} ({devices[-1].id})...")

try:
    API = Daikin(ip_address)
    print(API)
except requests.exceptions.ConnectionError as e:
    print(f"Failed to connect to Daikin AC at {ip_address}: {e}. Exit.")
    exit()

print(API.name)
print("API.inside_temperature", API.inside_temperature)

print(API.ATTRIBUTES)
