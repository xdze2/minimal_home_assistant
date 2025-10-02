#!/bin/bash
set -e

MOUNT_POINT="/media/data"
DEVICE="/dev/sda"
FSTAB="/etc/fstab"
LOCALUSER=$USER

# Create mount point if it doesn't exist
if [ ! -d "$MOUNT_POINT" ]; then
    echo "Creating mount point: $MOUNT_POINT"
    sudo mkdir -p "$MOUNT_POINT"
fi

# Set permissions (adjust as needed)
echo "Setting permissions on $MOUNT_POINT"
sudo chmod 755 "$MOUNT_POINT"
sudo chown $LOCALUSER:$LOCALUSER "$MOUNT_POINT"

# --- Check device exists ---
if [ ! -b "$DEVICE" ]; then
    echo "Error: $DEVICE does not exist!"
    exit 1
fi


# --- Ask to confirm before formatting ---
confirm() {
    read -rp "$1 [y/N]: " response
    [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]
}

echo "About to format $DEVICE as ext4 and mount at $MOUNT_POINT"
if ! confirm "Are you sure you want to ERASE ALL DATA on $DEVICE?"; then
    echo "Aborted."
    exit 0
fi

# --- Unmount if mounted ---
if mount | grep -q "^$DEVICE"; then
    echo "Unmounting $DEVICE..."
    sudo umount "$DEVICE"
fi

# --- Format device as ext4 ---
echo "Formatting $DEVICE to ext4..."
sudo mkfs.ext4 -F "$DEVICE"


# Check if entry already exists
if grep -q "^$DEVICE " "$FSTAB"; then
    echo "An entry for $DEVICE already exists in $FSTAB. Skipping..."
else
    echo "Adding entry to $FSTAB"

    echo "Backing up $FSTAB -> ${FSTAB}.bak"
    sudo cp "$FSTAB" "${FSTAB}.bak"

    echo "$DEVICE   $MOUNT_POINT   ext4   defaults,nofail   0   2" | sudo tee -a "$FSTAB"
fi

# 5. Mount immediately without reboot
echo "Mounting $DEVICE to $MOUNT_POINT"
sudo mount -a

echo "Done"
