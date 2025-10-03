import yaml


def set_nested_key(data: dict, key_path: list[str] | str, value: object) -> None:
    """Set a nested key in a dict, creating intermediate dicts as needed."""
    keys = key_path if isinstance(key_path, (list, tuple)) else key_path.split(".")
    d = data
    for k in keys[:-1]:
        if k not in d or not isinstance(d[k], dict):
            d[k] = {}
        d = d[k]
    d[keys[-1]] = value


def edit_yaml(filepath: str, key_path: list[str] | str, value: object) -> None:
    """
    Read a YAML file, add or modify a (possibly nested) key-value pair,
    and write the modified YAML back.
    key_path: list of keys or dot-separated string for nested keys.
    """
    with open(filepath, "r") as f:
        data = yaml.safe_load(f) or {}

    set_nested_key(data, key_path, value)

    with open(filepath, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)

    print(f"Updated YAML file {filepath}: '{key_path}' set to '{value}'")
