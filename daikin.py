from daikinapi import Daikin
import requests

ip_address = "192.168.1.73"  # Salon
ip_address = "192.168.1.84"  # Cuisine
print(f"Connecting to Daikin AC at {ip_address}...")

try:
    API = Daikin(ip_address)
    print(API)
except requests.exceptions.ConnectionError as e:
    print(f"Failed to connect to Daikin AC at {ip_address}: {e}. Exit.")
    exit()

print(API.name)
print("API.inside_temperature", API.inside_temperature)

print(API.ATTRIBUTES)
