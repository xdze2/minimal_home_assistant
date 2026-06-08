"""House model → RC network expansion.

expand(house, selection) → (model_dict, expansion_map)

selection: list of room/element UUIDs to include as active zones.
  - Selected rooms become mass nodes.
  - Unselected rooms referenced by a selected element become boundary nodes.
  - outdoor/ground elements referenced by any selected element become boundary nodes.
  - Elements where both sides are unselected are skipped entirely.

expansion_map: { house_uuid → list[rc_node_id] }
  Maps each house room/element UUID to the RC node ids it produced.
"""

from __future__ import annotations

import json
import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MATERIALS_DIR = Path(__file__).parents[1] / "data" / "materials"


def load_material_library() -> dict[str, dict]:
    """Load all *.json files from data/materials/ into a flat dict keyed by id."""
    lib: dict[str, dict] = {}
    if _MATERIALS_DIR.is_dir():
        for path in _MATERIALS_DIR.glob("*.json"):
            with open(path) as f:
                entry = json.load(f)
            mid = entry.get("id") or path.stem
            lib[mid] = entry
    return lib


_MATERIAL_LIBRARY: dict[str, dict] = load_material_library()

# ISO 6946 surface resistance defaults [m²·K/W]
_RSI_INTERIOR = 1.0 / 7.7   # h_i = 7.7 W/(m²·K)
_RSI_EXTERIOR = 1.0 / 25.0  # h_e = 25.0 W/(m²·K)

# Air properties for ACH → R conversion
_RHO_AIR = 1.2        # kg/m³
_CP_AIR  = 1006.0     # J/(kg·K)
_CP_AIR_KJ = _CP_AIR / 3600.0  # J/(kg·K) → Wh/(kg·K), used for ACH [h⁻¹] arithmetic


@dataclass
class _Builder:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    expansion_map: dict[str, list[str]] = field(default_factory=dict)
    _node_ids: set[str] = field(default_factory=set)

    def _unique_id(self, base: str) -> str:
        candidate = base
        n = 2
        while candidate in self._node_ids:
            candidate = f"{base}_{n}"
            n += 1
        self._node_ids.add(candidate)
        return candidate

    def add_node(self, node: dict, house_uuid: str | None = None) -> str:
        nid = node["id"]
        self._node_ids.add(nid)
        self.nodes.append(node)
        if house_uuid is not None:
            self.expansion_map.setdefault(house_uuid, []).append(nid)
        return nid

    def add_edge(self, from_id: str, to_id: str) -> None:
        self.edges.append({"from": from_id, "to": to_id})

    def has_node(self, nid: str) -> bool:
        return nid in self._node_ids

    def make_id(self, base: str) -> str:
        return self._unique_id(base)


def _safe_label(obj: dict) -> str:
    return obj.get("label") or obj.get("id", "")


def _room_volume(room: dict) -> float:
    return room["a"] * room["b"] * room["c"]


def _room_capacitance(room: dict) -> float:
    V = _room_volume(room)
    factor = room.get("furniture_factor", 2.5)
    return _RHO_AIR * _CP_AIR * V * factor


def _opaque_R_total(element: dict, materials: dict) -> float:
    """ISO 6946: R_total = R_si + sum(d/λ) + R_se, in K/W (not m²·K/W — area applied later)."""
    h_i = element.get("h_i", 7.7)
    h_e = element.get("h_e", 25.0)
    R_si = 1.0 / h_i
    R_se = 1.0 / h_e
    R_layers = sum(
        layer["thickness"] / materials[layer["material"]]["lambda"]
        for layer in element["layers"]
    )
    area = element["a"] * element["b"]
    # Convert m²·K/W → K/W
    return (R_si + R_layers + R_se) / area


def _ensure_zone_node(
    zone_uuid: str,
    all_zones: dict[str, dict],   # uuid → room or element dict
    selected: set[str],
    builder: _Builder,
) -> str:
    """Ensure a zone (room, outdoor, ground) has a node; return its node id."""
    node_id = f"z_{zone_uuid.replace('-', '')}"

    if builder.has_node(node_id):
        return node_id

    zone = all_zones[zone_uuid]
    kind = zone.get("kind")  # None for rooms

    if kind in ("outdoor", "ground"):
        # Always a boundary node
        if kind == "outdoor":
            T_source = zone.get("obs_signal") or "outdoor"
        else:
            T_source = 10.0  # ground: fixed 10 °C placeholder
        builder.add_node(
            {"id": node_id, "kind": "boundary", "label": _safe_label(zone), "T_source": T_source},
            house_uuid=zone_uuid,
        )
    elif zone_uuid in selected:
        # Selected room → mass node
        C = _room_capacitance(zone)
        builder.add_node(
            {"id": node_id, "kind": "mass", "label": _safe_label(zone), "C": C},
            house_uuid=zone_uuid,
        )
    else:
        # Unselected room → boundary node (temperature prescribed externally)
        builder.add_node(
            {"id": node_id, "kind": "boundary", "label": _safe_label(zone), "T_source": 20.0},
            house_uuid=zone_uuid,
        )

    return node_id


def _elem_base(element: dict) -> str:
    return element["id"].replace("-", "")


def _expand_opaque(element: dict, materials: dict, zone_a: str, zone_b: str, builder: _Builder) -> None:
    """Lumped opaque wall: single resistance node between zone_a and zone_b."""
    R = _opaque_R_total(element, materials)
    label = _safe_label(element)
    r_id = builder.make_id(f"R_{_elem_base(element)}")
    builder.add_node(
        {"id": r_id, "kind": "resistance", "label": label, "R": R},
        house_uuid=element["id"],
    )
    builder.add_edge(zone_a, r_id)
    builder.add_edge(r_id, zone_b)


def _expand_glazing(
    element: dict, zone_a: str, zone_b: str, builder: _Builder,
    outdoor_solar_signal: str | None = None,
) -> None:
    """Glazing: single resistance (from U-value) + optional solar source.

    Solar gain is included when the outdoor element has a solar_signal and the
    glazing has a SHGC value.  The source node carries gain = SHGC * area so
    the solver multiplies the raw irradiance [W/m²] by the effective aperture.
    """
    area = element["a"] * element["b"]
    R = 1.0 / (element["U"] * area)
    label = _safe_label(element)
    r_id = builder.make_id(f"R_{_elem_base(element)}")
    builder.add_node(
        {"id": r_id, "kind": "resistance", "label": f"{label} (U)", "R": R},
        house_uuid=element["id"],
    )
    builder.add_edge(zone_a, r_id)
    builder.add_edge(r_id, zone_b)

    # Solar gain source into the interior zone (zone_a)
    if element.get("SHGC") and outdoor_solar_signal:
        shgc = element["SHGC"]
        s_id = builder.make_id(f"solar_{_elem_base(element)}")
        builder.add_node(
            {
                "id": s_id,
                "kind": "source",
                "label": f"{label} (solar)",
                "signal": outdoor_solar_signal,
                "gain": shgc * area,
            },
            house_uuid=element["id"],
        )
        builder.add_edge(s_id, zone_a)


def _expand_air_exchange(
    element: dict, room: dict, zone_a: str, zone_b: str, builder: _Builder
) -> None:
    """Air exchange (infiltration/ventilation): R = 1 / (ṁ·cp) with ṁ = ρ·V·ACH/3600."""
    V = _room_volume(room)
    ach = element["ach"]
    m_dot = _RHO_AIR * V * ach / 3600.0   # kg/s
    G = m_dot * _CP_AIR                    # W/K
    R = 1.0 / G
    label = _safe_label(element)
    r_id = builder.make_id(f"R_ach_{_elem_base(element)}")
    builder.add_node(
        {"id": r_id, "kind": "resistance", "label": label, "R": R},
        house_uuid=element["id"],
    )
    builder.add_edge(zone_a, r_id)
    builder.add_edge(r_id, zone_b)


def expand(house: dict, selection: list[str]) -> tuple[dict, dict[str, list[str]]]:
    """Expand a house model dict into an RC network model dict + expansion_map.

    Parameters
    ----------
    house:     HouseModel dict (schema v0.2).
    selection: UUIDs of rooms/elements to include as active (mass) nodes.
               Unselected rooms that are connected to selected elements become
               boundary nodes. outdoor/ground are always boundary nodes.

    Returns
    -------
    model:          RC network dict conforming to model.schema.json v0.3.
    expansion_map:  { house_uuid → [rc_node_ids] }
    """
    selected = set(selection)
    materials = {**_MATERIAL_LIBRARY, **house.get("materials", {})}

    # Build a flat lookup: uuid → room or element dict
    all_zones: dict[str, dict] = {}
    for room in house["rooms"]:
        all_zones[room["id"]] = room
    for elem in house["elements"]:
        all_zones[elem["id"]] = elem

    builder = _Builder()

    # Find the outdoor element's solar_signal (if any) for use by glazing nodes
    outdoor_solar_signal: str | None = None
    for elem in house["elements"]:
        if elem.get("kind") == "outdoor" and elem.get("solar_signal"):
            outdoor_solar_signal = elem["solar_signal"]
            break

    # --- Rooms: create zone nodes for all rooms referenced in the selection
    # We also create nodes for outdoor/ground lazily as elements are processed.
    # Pre-create nodes for all selected rooms now so _ensure_zone_node finds them.
    for room in house["rooms"]:
        if room["id"] in selected:
            _ensure_zone_node(room["id"], all_zones, selected, builder)

    # --- Elements
    for elem in house["elements"]:
        kind = elem["kind"]

        if kind in ("outdoor", "ground"):
            # Created on demand when referenced by another element
            continue

        between = elem.get("between", [])
        if len(between) != 2:
            continue

        uuid_a, uuid_b = between[0], between[1]
        zone_a_selected = uuid_a in selected
        zone_b_selected = uuid_b in selected

        # Skip if neither side is a selected room
        if not (zone_a_selected or zone_b_selected):
            continue

        zone_a = _ensure_zone_node(uuid_a, all_zones, selected, builder)
        zone_b = _ensure_zone_node(uuid_b, all_zones, selected, builder)

        if kind == "opaque":
            _expand_opaque(elem, materials, zone_a, zone_b, builder)
        elif kind == "glazing":
            _expand_glazing(elem, zone_a, zone_b, builder, outdoor_solar_signal)
        elif kind == "air_exchange":
            # Need the room to compute volume; pick the side that is a room
            room_uuid = uuid_a if uuid_a in {r["id"] for r in house["rooms"]} else uuid_b
            room_dict = all_zones[room_uuid]
            _expand_air_exchange(elem, room_dict, zone_a, zone_b, builder)

    # --- Room signals (input_signal → source node, obs_signal noted in expansion_map)
    for room in house["rooms"]:
        if room["id"] not in selected:
            continue
        zone_id = f"z_{room['id'].replace('-', '')}"
        if room.get("input_signal"):
            src_id = builder.make_id(f"Q_{room['id'].replace('-', '')}")
            builder.add_node(
                {
                    "id": src_id,
                    "kind": "source",
                    "label": f"{_safe_label(room)} (input)",
                    "signal": room["input_signal"],
                    "gain": 1.0,
                },
                house_uuid=room["id"],
            )
            builder.add_edge(src_id, zone_id)

    model_id = f"expanded_{_uuid.uuid4().hex[:8]}"
    model = {
        "schema_version": "0.3",
        "id": model_id,
        "name": house.get("label", "Expanded model"),
        "nodes": builder.nodes,
        "edges": builder.edges,
    }

    return model, builder.expansion_map
