# miniha deployment helpers (Raspberry Pi target).
#
# Typical flow on the Pi:
#   make config       # one-time: seed config/sensors.yaml from the template
#   make install      # install systemd units + pip install -e .
#   make enable       # enable + start the units below
#   make update       # git pull && reinstall + restart
#
# Override with `make VAR=value <target>` if your layout differs.

REPO_DIR      := $(abspath $(CURDIR))
VENV          ?= $(REPO_DIR)/venv
PIP           := $(VENV)/bin/pip
SYSTEMD_DIR   ?= /etc/systemd/system
SYSTEMD_SRC   := $(REPO_DIR)/config/systemd
SENSORS_FILE  := $(REPO_DIR)/config/sensors.yaml
SENSORS_TPL   := $(REPO_DIR)/config/sensors.example.yaml

UNITS := \
  daikin_to_influx.service \
  mqtt_to_influx.service \
  miniha_webapp.service \
  open_meteo_to_influx.service \
  open_meteo_to_influx.timer

# Units that should run continuously (services). Timers go in TIMERS below.
ENABLE_SERVICES := \
  daikin_to_influx.service \
  mqtt_to_influx.service \
  miniha_webapp.service

ENABLE_TIMERS := \
  open_meteo_to_influx.timer

.PHONY: help config install enable disable update restart status uninstall

help:
	@echo "Targets:"
	@echo "  config     Seed config/sensors.yaml from the template (won't overwrite)."
	@echo "  install    Copy systemd units and pip install -e . into \$$VENV."
	@echo "  enable     Enable + start configured services and timers."
	@echo "  disable    Stop + disable configured services and timers."
	@echo "  update     git pull && install && restart services."
	@echo "  restart    Restart configured services (timers stay as-is)."
	@echo "  status     Show status of configured units."
	@echo "  uninstall  Remove unit symlinks from $(SYSTEMD_DIR)."

config:
	@if [ -f $(SENSORS_FILE) ]; then \
	  echo "$(SENSORS_FILE) already exists — leaving it alone."; \
	else \
	  cp $(SENSORS_TPL) $(SENSORS_FILE); \
	  echo "Created $(SENSORS_FILE) from template. Edit it before running services."; \
	fi

install:
	@if [ ! -x $(PIP) ]; then \
	  echo "No venv at $(VENV). Create one first: python3 -m venv $(VENV)"; exit 1; \
	fi
	$(PIP) install -e .
	@for unit in $(UNITS); do \
	  echo "Installing $$unit -> $(SYSTEMD_DIR)/"; \
	  sudo ln -sf $(SYSTEMD_SRC)/$$unit $(SYSTEMD_DIR)/$$unit; \
	done
	sudo systemctl daemon-reload

enable:
	@for unit in $(ENABLE_SERVICES) $(ENABLE_TIMERS); do \
	  echo "Enabling $$unit"; \
	  sudo systemctl enable --now $$unit; \
	done

disable:
	@for unit in $(ENABLE_SERVICES) $(ENABLE_TIMERS); do \
	  echo "Disabling $$unit"; \
	  sudo systemctl disable --now $$unit || true; \
	done

restart:
	@for unit in $(ENABLE_SERVICES); do \
	  echo "Restarting $$unit"; \
	  sudo systemctl restart $$unit; \
	done

update:
	git pull --ff-only
	$(MAKE) install
	$(MAKE) restart

status:
	@for unit in $(ENABLE_SERVICES) $(ENABLE_TIMERS); do \
	  systemctl status --no-pager --lines=3 $$unit || true; \
	  echo; \
	done

uninstall:
	@for unit in $(UNITS); do \
	  if [ -L $(SYSTEMD_DIR)/$$unit ]; then \
	    echo "Removing $(SYSTEMD_DIR)/$$unit"; \
	    sudo rm $(SYSTEMD_DIR)/$$unit; \
	  fi; \
	done
	sudo systemctl daemon-reload
