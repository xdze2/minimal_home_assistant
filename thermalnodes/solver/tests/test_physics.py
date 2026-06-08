"""Tests for solver/physics.py — expand(house, selection)."""

import json
from pathlib import Path

import pytest

from thermalnodes.solver.physics import expand
from thermalnodes.solver.assemble import assemble

DATA = Path(__file__).parents[2] / "data"

with open(DATA / "house.json") as f:
    HOUSE = json.load(f)

# Convenience: UUIDs from house.json
ROOM_CHAMBRE  = "a1b2c3d4-0001-0000-0000-000000000001"
OUTDOOR       = "a1b2c3d4-0001-0000-0000-000000000002"
GROUND        = "a1b2c3d4-0001-0000-0000-000000000003"
OPAQUE_MUR_SE = "a1b2c3d4-0001-0000-0000-000000000004"
GLAZING_SE    = "a1b2c3d4-0001-0000-0000-000000000005"
AIR_EXCH      = "a1b2c3d4-0001-0000-0000-000000000006"


class TestExpandChambreOnly:
    def setup_method(self):
        self.model, self.emap = expand(HOUSE, [ROOM_CHAMBRE])

    def test_schema_version(self):
        assert self.model["schema_version"] == "0.3"

    def _zone_node_id(self, uuid: str) -> str:
        return f"z_{uuid.replace('-', '')}"

    def test_chambre_is_mass(self):
        kinds = {n["id"]: n["kind"] for n in self.model["nodes"]}
        chambre_node = self._zone_node_id(ROOM_CHAMBRE)
        assert chambre_node in kinds
        assert kinds[chambre_node] == "mass"

    def test_outdoor_is_boundary(self):
        kinds = {n["id"]: n["kind"] for n in self.model["nodes"]}
        outdoor_node = self._zone_node_id(OUTDOOR)
        assert outdoor_node in kinds
        assert kinds[outdoor_node] == "boundary"

    def test_expansion_map_chambre(self):
        assert ROOM_CHAMBRE in self.emap
        assert len(self.emap[ROOM_CHAMBRE]) >= 1

    def test_expansion_map_outdoor(self):
        assert OUTDOOR in self.emap

    def test_expansion_map_elements_present(self):
        assert OPAQUE_MUR_SE in self.emap
        assert GLAZING_SE in self.emap
        assert AIR_EXCH in self.emap

    def test_assembles_without_error(self):
        sys = assemble(self.model)
        assert sys.A.shape[0] >= 1

    def test_mass_node_count(self):
        sys = assemble(self.model)
        assert len(sys.mass_ids) == 1  # chambre only

    def test_A_stable(self):
        import numpy as np
        sys = assemble(self.model)
        eigs = np.linalg.eigvals(sys.A).real
        assert all(e < 0 for e in eigs)

    def test_energy_conservation(self):
        """Each row of A + matching B_boundary row must sum to ~0."""
        import numpy as np
        sys = assemble(self.model)
        for i in range(len(sys.mass_ids)):
            row_sum = sys.A[i, :].sum() + sys.B_boundary[i, :].sum()
            assert abs(row_sum) < 1e-8, f"row {i} energy imbalance: {row_sum:.2e}"

    def test_solar_source_present(self):
        """Glazing with SHGC should produce a solar source node referencing outdoor solar_signal."""
        outdoor_elem = next(e for e in HOUSE["elements"] if e["id"] == OUTDOOR)
        solar_signal = outdoor_elem.get("solar_signal")
        source_nodes = [n for n in self.model["nodes"] if n["kind"] == "source"]
        assert any(n["signal"] == solar_signal for n in source_nodes)

    def test_solar_source_gain(self):
        """Glazing solar source gain should equal SHGC * area."""
        glazing_elem = next(e for e in HOUSE["elements"] if e["id"] == GLAZING_SE)
        expected_gain = glazing_elem["SHGC"] * glazing_elem["a"] * glazing_elem["b"]
        source_nodes = [n for n in self.model["nodes"] if n["kind"] == "source"]
        gains = [n["gain"] for n in source_nodes]
        assert any(abs(g - expected_gain) < 1e-9 for g in gains)

    def test_obs_signal_on_boundary(self):
        """outdoor boundary node T_source should reflect the obs_signal."""
        outdoor_node = self._zone_node_id(OUTDOOR)
        node = next(n for n in self.model["nodes"] if n["id"] == outdoor_node)
        outdoor_elem = next(e for e in HOUSE["elements"] if e["id"] == OUTDOOR)
        assert node["T_source"] == outdoor_elem["obs_signal"]


class TestExpandEmptySelection:
    def test_empty_selection_produces_no_mass(self):
        model, emap = expand(HOUSE, [])
        sys = assemble(model)
        assert len(sys.mass_ids) == 0

    def test_empty_selection_model_valid(self):
        model, emap = expand(HOUSE, [])
        assert "nodes" in model
        assert "edges" in model


class TestExpandTwoRooms:
    """House with two rooms: selecting both should wire the shared wall correctly."""

    HOUSE_2R = {
        "schema_version": "0.2",
        "label": "Two rooms",
        "materials": {
            "brick": {"lambda": 0.8, "rho": 1800, "cp": 840}
        },
        "rooms": [
            {"id": "r1", "label": "Room1", "a": 4, "b": 4, "c": 2.5},
            {"id": "r2", "label": "Room2", "a": 3, "b": 4, "c": 2.5},
        ],
        "elements": [
            {"id": "out1", "kind": "outdoor", "label": "Ext",
             "obs_signal": "open_meteo_historic/temperature_2m?location=home"},
            {"id": "wall_shared", "kind": "opaque", "label": "Shared wall",
             "between": ["r1", "r2"], "a": 4.0, "b": 2.5,
             "layers": [{"material": "brick", "thickness": 0.2}]},
            {"id": "wall_ext", "kind": "opaque", "label": "Ext wall",
             "between": ["r1", "out1"], "a": 4.0, "b": 2.5,
             "layers": [{"material": "brick", "thickness": 0.3}]},
        ],
    }

    def test_both_rooms_selected_gives_two_masses(self):
        model, emap = expand(self.HOUSE_2R, ["r1", "r2"])
        sys = assemble(model)
        assert len(sys.mass_ids) == 2

    def test_shared_wall_in_emap(self):
        _, emap = expand(self.HOUSE_2R, ["r1", "r2"])
        assert "wall_shared" in emap

    def test_one_room_selected_other_becomes_boundary(self):
        model, emap = expand(self.HOUSE_2R, ["r1"])
        sys = assemble(model)
        assert len(sys.mass_ids) == 1
        assert len(sys.boundary_ids) == 2  # r2 + outdoor

    def test_energy_conservation_two_rooms(self):
        import numpy as np
        model, _ = expand(self.HOUSE_2R, ["r1", "r2"])
        sys = assemble(model)
        for i in range(len(sys.mass_ids)):
            row_sum = sys.A[i, :].sum() + sys.B_boundary[i, :].sum()
            assert abs(row_sum) < 1e-8, f"row {i} energy imbalance: {row_sum:.2e}"
