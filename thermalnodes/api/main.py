"""FastAPI backend for thermalnodes.

Run:
    uv run uvicorn thermalnodes.api.main:app --reload --port 8001
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .influx import fetch_series, list_signals
from ..solver.assemble import assemble
from ..solver.simulate import simulate_ivp, simulate_zoh, simulate_mock

app = FastAPI(title="thermalnodes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
