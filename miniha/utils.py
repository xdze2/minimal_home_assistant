from typing import Union
from datetime import datetime, date


def normalize_to_datetime(val: Union[str, date]) -> datetime:
    """Convert a string or date to a datetime object."""
    # TODO enforce UTC
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    if isinstance(val, str):
        # Try parsing ISO format first
        try:
            return datetime.fromisoformat(val)
        except ValueError:
            # Try common date formats if needed
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(val, fmt)
                except ValueError:
                    continue
        raise ValueError(f"Cannot parse date string: {val}")
    raise TypeError(f"Unsupported type: {type(val)}")
