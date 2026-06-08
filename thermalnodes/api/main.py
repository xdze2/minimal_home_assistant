"""FastAPI backend for thermalnodes.

Run:
    uv run uvicorn thermalnodes.api.main:app --reload --port 8001
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .influx import fetch_series, list_signals
from ..solver.assemble import assemble
from ..solver.simulate import simulate_ivp, simulate_zoh, simulate_mock
from ..solver.fit import build_forward, fit_nls, fit_mcmc
from ..solver.identifiability import group_params
from ..solver.physics import expand

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


class ExpandRequest(BaseModel):
    house: dict
    selection: list[str]


@app.post("/house/expand")
def post_house_expand(req: ExpandRequest) -> dict:
    """Preview expand(house, selection) — returns rc_model + expansion_map, no persist."""
    try:
        model, expansion_map = expand(req.house, req.selection)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"model": model, "expansion_map": expansion_map}


class FromHouseRequest(BaseModel):
    house: dict
    selection: list[str]
    label: str = ""


@app.post("/studies/from_house")
def post_studies_from_house(req: FromHouseRequest) -> dict:
    """Expand the house selection into a new study JSON and persist it.

    Returns {"ok": True, "id": study_id, "model": ...}.
    """
    try:
        model, expansion_map = expand(req.house, req.selection)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    study_id = str(uuid.uuid4())
    label = req.label.strip() or model.get("name", study_id)
    model["name"] = label

    # Pre-populate inputs from embedded signals on model nodes so the study
    # is ready to run without manual wiring in the Inputs panel.
    auto_inputs: dict[str, str] = {}
    for node in model.get("nodes", []):
        if node["kind"] == "boundary":
            t_src = node.get("T_source")
            if isinstance(t_src, str):  # string = signal name; float = fixed value
                auto_inputs[node["id"]] = t_src
        elif node["kind"] == "source":
            sig = node.get("signal")
            if sig:
                auto_inputs[node["id"]] = sig

    study = {
        "id":            study_id,
        "label":         label,
        "model":         model,
        "expansion_map": expansion_map,
        "inputs":        auto_inputs,
        "observations":  {},
        "start":         "",
        "end":           "",
        "solver":        "zoh",
    }
    dest = STUDIES_DIR / f"{study_id}.json"
    dest.write_text(json.dumps(study, indent=2, ensure_ascii=False))
    return {"ok": True, "id": study_id, "model": model}


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


@app.post("/studies/{study_id}/duplicate")
def duplicate_study(study_id: str) -> dict:
    source = get_study(study_id)  # raises 404 if not found
    new_id = str(uuid.uuid4())
    source["id"] = new_id
    dest = STUDIES_DIR / f"{new_id}.json"
    dest.write_text(json.dumps(source, indent=2, ensure_ascii=False))
    return {"ok": True, "id": new_id}


# ── simulate ──────────────────────────────────────────────────────────────────

class SimulateRequest(BaseModel):
    model: dict
    start: str
    end: str
    inputs: dict[str, str]  # node_id → signal name
    solver: str = "ivp"     # "ivp" | "zoh"
    dt_minutes: int = 15    # ZOH time step (ignored for ivp)



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


# ── fit ───────────────────────────────────────────────────────────────────────

class PreviewGroupsRequest(BaseModel):
    model: dict
    param_keys: list[str]


@app.post("/fit/preview-groups")
def post_fit_preview_groups(req: PreviewGroupsRequest) -> list[list[str]]:
    """Return identifiability groups for the given model and free param keys.

    Groups with more than one element contain parallel-path resistors whose
    individual values cannot be distinguished — only their combined conductance
    is observable from the state vector.
    """
    try:
        return group_params(req.model, req.param_keys)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class FitRequest(BaseModel):
    model: dict
    start: str
    end: str
    inputs: dict[str, str]       # node_id → signal name
    observations: dict[str, str] # mass_node_id → signal name
    params: dict[str, dict]      # param_key → {nominal, sigma_log}
    obs_sigma: float = 0.5
    method: str = "nls"          # "nls" | "mcmc"
    dt_minutes: int = 15


@app.post("/fit/run")
def post_fit_run(req: FitRequest) -> dict:
    """Fetch inputs + observations from InfluxDB, then run NLS or MCMC fit.

    Returns fitted parameter values, uncertainties, and diagnostics.
    """
    import numpy as np

    # Fetch input signals
    inputs: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    errors: dict[str, str] = {}
    for node_id, signal_name in req.inputs.items():
        try:
            s = fetch_series(signal_name, req.start, req.end)
            t_sec = s.index.astype("int64") / 1e9
            inputs[node_id] = (t_sec.to_numpy(), s.to_numpy(dtype=float))
        except Exception as e:
            errors[node_id] = str(e)

    # Fetch observation signals
    observations: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for node_id, signal_name in req.observations.items():
        try:
            s = fetch_series(signal_name, req.start, req.end)
            t_sec = s.index.astype("int64") / 1e9
            observations[node_id] = (t_sec.to_numpy(), s.to_numpy(dtype=float))
        except Exception as e:
            errors[node_id] = str(e)

    if errors:
        raise HTTPException(
            status_code=400,
            detail={"message": "Failed to fetch some signals", "errors": errors},
        )

    fit_config = {
        "params":    req.params,
        "obs_sigma": req.obs_sigma,
        "method":    req.method,
    }

    try:
        forward_fn, log_p0, param_keys, groups = build_forward(
            req.model, inputs, observations, fit_config,
            req.start, req.end, req.dt_minutes,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Model error: {e}") from e

    try:
        if req.method == "mcmc":
            result = fit_mcmc(forward_fn, log_p0, param_keys, fit_config, groups=groups)
            return {
                "method":          result.method,
                "params_nominal":  result.params_nominal,
                "params_mean":     result.params_mean,
                "params_std":      result.params_std,
                "acceptance_rate": result.acceptance_rate,
                "elapsed_s":       result.elapsed_s,
                "param_groups":    groups,
            }
        else:
            result = fit_nls(forward_fn, log_p0, param_keys, fit_config, groups=groups)
            return {
                "method":          result.method,
                "params_nominal":  result.params_nominal,
                "params_fitted":   result.params_fitted,
                "params_std":      result.params_std,
                "cost":            result.cost,
                "success":         result.success,
                "message":         result.message,
                "elapsed_s":       result.elapsed_s,
                "n_evals":         result.n_evals,
                "param_groups":    groups,
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fit error: {e}") from e


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
