"""FastAPI backend for thermalnodes.

Run:
    uv run uvicorn thermalnodes.api.main:app --reload --port 8001
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .influx import fetch_series, list_signals
from ..solver.assemble import assemble
from ..solver.simulate import simulate_ivp, simulate_zoh, simulate_mock

DATA_DIR     = Path(__file__).parent.parent / "data"
EXAMPLES_DIR = DATA_DIR / "examples"
STUDIES_DIR  = DATA_DIR / "user" / "studies"
HOUSE_FILE   = DATA_DIR / "house.json"

STUDIES_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="thermalnodes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── house ────────────────────────────────────────────────────────────────────

@app.get("/house")
def get_house() -> dict:
    if not HOUSE_FILE.exists():
        raise HTTPException(status_code=404, detail="house.json not found")
    return json.loads(HOUSE_FILE.read_text())


@app.post("/house")
def post_house(body: dict) -> dict:
    HOUSE_FILE.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    return {"ok": True}


# ── studies ───────────────────────────────────────────────────────────────────

def _load_study(path: Path, source: str) -> dict:
    data = json.loads(path.read_text())
    study_id = path.stem
    return {
        "id":     data.get("id", study_id),
        "label":  data.get("label") or data.get("name") or study_id,
        "room":   data.get("room", None),
        "source": source,
    }


@app.get("/studies")
def get_studies() -> list[dict]:
    studies = []
    for p in sorted(EXAMPLES_DIR.glob("*.json")):
        try:
            studies.append(_load_study(p, "example"))
        except Exception:
            pass
    for p in sorted(STUDIES_DIR.glob("*.json")):
        try:
            studies.append(_load_study(p, "user"))
        except Exception:
            pass
    return studies


@app.get("/studies/{study_id}")
def get_study(study_id: str) -> dict:
    user_path = STUDIES_DIR / f"{study_id}.json"
    if user_path.exists():
        return json.loads(user_path.read_text())
    example_path = EXAMPLES_DIR / f"{study_id}.json"
    if example_path.exists():
        return json.loads(example_path.read_text())
    raise HTTPException(status_code=404, detail=f"Study '{study_id}' not found")


def _valid_id(study_id: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_\-]+", study_id))


@app.post("/studies/{study_id}")
def post_study(study_id: str, body: dict) -> dict:
    if not _valid_id(study_id):
        raise HTTPException(status_code=400, detail="Invalid study id (alphanumeric, _ and - only)")
    path = STUDIES_DIR / f"{study_id}.json"
    body["id"] = study_id
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    return {"ok": True, "id": study_id}


class DuplicateRequest(BaseModel):
    new_id: str


@app.post("/studies/{study_id}/duplicate")
def duplicate_study(study_id: str, req: DuplicateRequest) -> dict:
    if not _valid_id(req.new_id):
        raise HTTPException(status_code=400, detail="Invalid new_id")
    source = get_study(study_id)  # raises 404 if not found
    source["id"] = req.new_id
    dest = STUDIES_DIR / f"{req.new_id}.json"
    dest.write_text(json.dumps(source, indent=2, ensure_ascii=False))
    return {"ok": True, "id": req.new_id}


# ── simulate ──────────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    model: dict
    start: str
    end: str
    inputs: dict[str, str]  # node_id → signal name
    solver: str = "ivp"     # "ivp" | "zoh"
    dt_minutes: int = 15    # ZOH time step (ignored for ivp)


@app.post("/simulate/inputs")
def post_simulate_inputs(req: SimulateRequest) -> dict:
    """Fetch and resample all input signals for a simulation config.

    Returns:
        { node_id: { "signal": str, "t": [ISO strings], "values": [floats | null] } }
    """
    result = {}
    errors = {}
    for node_id, signal_name in req.inputs.items():
        try:
            s = fetch_series(signal_name, req.start, req.end)
            result[node_id] = {
                "signal": signal_name,
                "t": [ts.isoformat() for ts in s.index],
                "values": [None if v != v else float(v) for v in s],
            }
        except Exception as e:
            errors[node_id] = str(e)

    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Failed to fetch some signals", "errors": errors},
        )
    return result


@app.post("/simulate/run")
def post_simulate_run(req: SimulateRequest) -> dict:
    """Fetch inputs from InfluxDB and run the real IVP solver.

    Returns:
        {
            "t": [ISO strings],
            "nodes": { mass_id: [float, ...] },
            "meta": { solver, elapsed_s, n_steps, n_rhs_evals, success, message }
        }
    """
    import datetime
    import numpy as np

    try:
        system = assemble(req.model)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Model assembly error: {e}") from e

    # Fetch and resample all input signals
    inputs: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    errors: dict[str, str] = {}
    for node_id, signal_name in req.inputs.items():
        try:
            s = fetch_series(signal_name, req.start, req.end)
            t_sec = s.index.astype("int64") / 1e9
            inputs[node_id] = (t_sec.to_numpy(), s.to_numpy(dtype=float))
        except Exception as e:
            errors[node_id] = str(e)

    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Failed to fetch some signals", "errors": errors},
        )

    try:
        if req.solver == "zoh":
            result = simulate_zoh(system, inputs, req.start, req.end, req.dt_minutes)
        else:
            result = simulate_ivp(system, inputs, req.start, req.end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}") from e

    if not result.success:
        raise HTTPException(status_code=500, detail=f"Solver failed: {result.message}")

    t_iso = [
        datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
        for ts in result.t
    ]
    return {
        "t": t_iso,
        "nodes": {mid: list(arr) for mid, arr in result.temps.items()},
        "meta": {
            "solver": result.solver,
            "elapsed_s": result.elapsed_s,
            "n_steps": result.n_steps,
            "n_rhs_evals": result.n_rhs_evals,
            "success": result.success,
            "message": result.message,
        },
    }


@app.post("/simulate")
def post_simulate(req: SimulateRequest) -> dict:
    """Run a simulation and return temperature time-series per mass node.

    Returns:
        { "t": [ISO strings], "nodes": { mass_id: [float, ...] } }
    """
    try:
        system = assemble(req.model)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Model assembly error: {e}") from e

    try:
        result = simulate_mock(system, req.start, req.end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Simulation error: {e}") from e

    import datetime
    t_iso = [
        datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).isoformat()
        for ts in result.t
    ]
    return {
        "t": t_iso,
        "nodes": {mid: list(arr) for mid, arr in result.temps.items()},
    }


@app.get("/signals")
def get_signals() -> list[str]:
    """List all available signal names from InfluxDB.

    Format: 'measurement/field' or 'measurement/field?tag=value'.
    Used by the Svelte UI to populate signal-name autocomplete.
    """
    try:
        return list_signals()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"InfluxDB unreachable: {e}") from e


@app.get("/series")
def get_series(
    signal: str = Query(..., description="measurement/field?tag=val"),
    start: str = Query(..., description="ISO-8601 start time"),
    end: str = Query(..., description="ISO-8601 end time"),
    resample: str = Query("15min", description="pandas resample offset"),
) -> dict:
    """Fetch one signal, resampled to a uniform grid.

    Returns:
        { "signal": str, "t": [ISO strings], "values": [floats | null] }
    """
    try:
        s = fetch_series(signal, start, end, resample=resample)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"InfluxDB error: {e}") from e

    return {
        "signal": signal,
        "t": [ts.isoformat() for ts in s.index],
        "values": [None if v != v else float(v) for v in s],  # NaN → null
    }
