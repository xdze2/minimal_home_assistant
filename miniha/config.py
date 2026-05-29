"""Runtime configuration for miniha.

Values come from environment variables, with a `.env` file loaded at import
time if present. Override the path with `MINIHA_ENV_FILE` (e.g. for systemd).
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal `.env` loader: `KEY=VALUE` per line, `#` comments, optional quotes.

    Existing environment variables win (so systemd `Environment=` overrides
    `.env`). No interpolation, no multiline values — keep it boring.
    """
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV = _REPO_ROOT / ".env"
_load_dotenv(Path(os.environ.get("MINIHA_ENV_FILE", _DEFAULT_ENV)))


class Config:
    INFLUX_HOST = os.environ.get("MINIHA_INFLUX_HOST", "localhost")
    INFLUX_PORT = int(os.environ.get("MINIHA_INFLUX_PORT", "8086"))
    INFLUX_DB = os.environ.get("MINIHA_INFLUX_DB", "sensors2")

    MQTT_HOST = os.environ.get("MINIHA_MQTT_HOST", "localhost")
    MQTT_PORT = int(os.environ.get("MINIHA_MQTT_PORT", "1883"))

    WEBAPP_PORT = int(os.environ.get("MINIHA_PORT", "5001"))

    OUTPUT_DIR = os.environ.get("MINIHA_OUTPUT_DIR", "output")


config = Config()
