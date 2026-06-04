"""
Streamlit demo: a + b + c = 0
All three (a, b, c) are parameters with configurable priors.
The model is: observe y = 0 = a + b + c (soft constraint with noise sigma_y).
Inference via importance sampling from the prior — exact, no MCMC trapping.
"""

import numpy as np
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# Inference  (importance sampling from the prior)
# ---------------------------------------------------------------------------

def run_inference(
    a_mu: float,
    a_sigma: float,
    b_mix_mu: list[float],
    b_mix_sigma: list[float],
    b_mix_weights: list[float],
    c_mu: float,
    c_sigma: float,
    sigma_y: float,
    n_samples: int = 200_000,
    seed: int = 0,
) -> dict:
    rng = np.random.default_rng(seed)

    # Sample from prior
    a = rng.normal(a_mu, a_sigma, size=n_samples)

    w = np.array(b_mix_weights, dtype=float)
    w /= w.sum()
    comp = rng.choice(len(w), size=n_samples, p=w)
    b_mus = np.array(b_mix_mu)[comp]
    b_sigs = np.array(b_mix_sigma)[comp]
    b = rng.normal(b_mus, b_sigs)

    c = rng.normal(c_mu, c_sigma, size=n_samples)

    # Importance weights: likelihood of observing y=0
    log_w = -0.5 * ((a + b + c) / sigma_y) ** 2
    log_w -= log_w.max()
    weights = np.exp(log_w)
    weights /= weights.sum()

    # Effective sample size
    ess = 1.0 / (weights ** 2).sum()

    # Resample
    idx = rng.choice(n_samples, size=n_samples, replace=True, p=weights)
    return {"a": a[idx], "b": b[idx], "c": c[idx], "ess": ess}


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def _gaussian_pdf(x, mu, sigma):
    return np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))


def _prior_b_pdf(x: np.ndarray, mus, sigmas, weights) -> np.ndarray:
    w = np.array(weights, dtype=float)
    w /= w.sum()
    pdf = np.zeros_like(x, dtype=float)
    for mu, sigma, wi in zip(mus, sigmas, w):
        pdf += wi * _gaussian_pdf(x, mu, sigma)
    return pdf


def plot_marginal(samples: np.ndarray, var: str, prior_x, prior_pdf, x_range: tuple) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=samples,
        histnorm="probability density",
        nbinsx=80,
        name="posterior (IS)",
        marker_color="steelblue",
        opacity=0.6,
        xbins=dict(start=x_range[0], end=x_range[1],
                   size=(x_range[1] - x_range[0]) / 80),
    ))
    fig.add_trace(go.Scatter(
        x=prior_x, y=prior_pdf, mode="lines", name="prior",
        line=dict(color="orange", width=2.5),
    ))
    fig.update_layout(
        title=var, xaxis_title=var, yaxis_title="density",
        height=300, margin=dict(t=40, b=20), barmode="overlay",
        legend=dict(orientation="h", y=1.15),
        xaxis=dict(range=x_range),
    )
    return fig


def plot_joint(result: dict) -> go.Figure:
    from plotly.subplots import make_subplots

    a, b, c = result["a"], result["b"], result["c"]
    n = min(5000, len(a))
    idx = np.random.choice(len(a), size=n, replace=False)
    kw = dict(mode="markers", marker=dict(size=3, opacity=0.3))

    fig = make_subplots(rows=1, cols=3, subplot_titles=["(a, b)", "(a, c)", "(b, c)"])
    fig.add_trace(go.Scatter(x=a[idx], y=b[idx], name="(a,b)", **kw), row=1, col=1)
    fig.add_trace(go.Scatter(x=a[idx], y=c[idx], name="(a,c)", **kw), row=1, col=2)
    fig.add_trace(go.Scatter(x=b[idx], y=c[idx], name="(b,c)", **kw), row=1, col=3)
    fig.update_xaxes(title_text="a", row=1, col=1)
    fig.update_yaxes(title_text="b", row=1, col=1)
    fig.update_xaxes(title_text="a", row=1, col=2)
    fig.update_yaxes(title_text="c", row=1, col=2)
    fig.update_xaxes(title_text="b", row=1, col=3)
    fig.update_yaxes(title_text="c", row=1, col=3)
    fig.update_layout(height=350, margin=dict(t=50, b=30), showlegend=False)
    return fig


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Simple Bayes demo: a+b+c=0", layout="wide")
st.title("Simple Bayesian demo: a + b + c = 0")
st.caption(
    "All three (_a_, _b_, _c_) have independent priors. "
    "The model observes _y_ = 0 = _a_ + _b_ + _c_ (soft constraint with noise σ_y). "
    "Inference via **importance sampling** from the prior — exact, no MCMC."
)

# --- Sidebar ---
with st.sidebar:
    st.header("Prior on a (Gaussian)")
    a_mu = st.number_input("a prior mean", value=0.0, step=0.1)
    a_sigma = st.number_input("a prior std", value=2.0, min_value=0.01, step=0.1)

    st.header("Prior on c (Gaussian)")
    c_mu = st.number_input("c prior mean", value=0.0, step=0.1)
    c_sigma = st.number_input("c prior std", value=2.0, min_value=0.01, step=0.1)

    st.header("Prior on b (mixture of Gaussians)")

    if "b_components" not in st.session_state:
        st.session_state.b_components = [
            {"mu": -2.0, "sigma": 0.5, "weight": 1.0},
            {"mu":  2.0, "sigma": 0.5, "weight": 1.0},
        ]

    col_add, col_rm = st.columns(2)
    if col_add.button("+ Add component"):
        st.session_state.b_components.append({"mu": 0.0, "sigma": 1.0, "weight": 1.0})
    if col_rm.button("- Remove last") and len(st.session_state.b_components) > 1:
        st.session_state.b_components.pop()

    components = st.session_state.b_components
    for i, comp in enumerate(components):
        st.markdown(f"**Component {i+1}**")
        c1, c2, c3 = st.columns(3)
        comp["mu"] = c1.number_input(f"μ_{i+1}", value=comp["mu"], key=f"mu_{i}", step=0.1)
        comp["sigma"] = c2.number_input(f"σ_{i+1}", value=comp["sigma"], min_value=0.01, key=f"sig_{i}", step=0.1)
        comp["weight"] = c3.number_input(f"w_{i+1}", value=comp["weight"], min_value=0.01, key=f"w_{i}", step=0.1)

    st.header("Constraint noise")
    sigma_y = st.number_input("σ_y (noise on y = a+b+c)", value=0.1, min_value=1e-4, step=0.01, format="%.3f")

    st.header("Sampler")
    n_samples = st.select_slider("Prior samples", [10_000, 50_000, 200_000, 500_000], value=200_000)
    is_seed = st.number_input("Seed", value=0, step=1)

    run_button = st.button("Run inference", type="primary")

b_mix_mu = [c["mu"] for c in components]
b_mix_sigma = [c["sigma"] for c in components]
b_mix_weights = [c["weight"] for c in components]

# --- Run ---
if run_button:
    with st.spinner("Sampling..."):
        result = run_inference(
            a_mu=a_mu, a_sigma=a_sigma,
            b_mix_mu=b_mix_mu, b_mix_sigma=b_mix_sigma, b_mix_weights=b_mix_weights,
            c_mu=c_mu, c_sigma=c_sigma,
            sigma_y=sigma_y,
            n_samples=int(n_samples),
            seed=int(is_seed),
        )
        st.session_state["result"] = result

# --- Main area ---
tab_marginals, tab_posterior = st.tabs(["Marginals", "Posterior (joint)"])

result = st.session_state.get("result")

with tab_marginals:
    if result is not None:
        ess = result["ess"]
        st.caption(f"Effective sample size (ESS): **{ess:.0f}** / {n_samples:,}  —  ESS ratio: {ess/n_samples:.3f}")
        if ess < 1000:
            st.warning("Low ESS: increase prior samples or widen σ_y.")

        all_s = np.concatenate([result["a"], result["b"], result["c"]])
        padding = max(a_sigma, max(b_mix_sigma), c_sigma)
        x_min = all_s.min() - padding
        x_max = all_s.max() + padding
        x_range = (x_min, x_max)
        x = np.linspace(x_min, x_max, 400)

        st.plotly_chart(plot_marginal(result["a"], "a", x, _gaussian_pdf(x, a_mu, a_sigma), x_range), use_container_width=True)
        st.plotly_chart(plot_marginal(result["b"], "b", x, _prior_b_pdf(x, b_mix_mu, b_mix_sigma, b_mix_weights), x_range), use_container_width=True)
        st.plotly_chart(plot_marginal(result["c"], "c", x, _gaussian_pdf(x, c_mu, c_sigma), x_range), use_container_width=True)
    else:
        # Prior only
        padding = max(a_sigma, max(b_mix_sigma), c_sigma)
        x_min = min(a_mu - 3*a_sigma, min(b_mix_mu) - 3*max(b_mix_sigma), c_mu - 3*c_sigma) - padding
        x_max = max(a_mu + 3*a_sigma, max(b_mix_mu) + 3*max(b_mix_sigma), c_mu + 3*c_sigma) + padding
        x_range = (x_min, x_max)
        x = np.linspace(x_min, x_max, 400)

        for var, pdf in [
            ("a", _gaussian_pdf(x, a_mu, a_sigma)),
            ("b", _prior_b_pdf(x, b_mix_mu, b_mix_sigma, b_mix_weights)),
            ("c", _gaussian_pdf(x, c_mu, c_sigma)),
        ]:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x, y=pdf, mode="lines", name=f"prior({var})", line=dict(color="orange", width=2.5)))
            fig.update_layout(title=f"{var}  (prior only)", xaxis_title=var, yaxis_title="density",
                              height=300, margin=dict(t=40, b=20), xaxis=dict(range=x_range))
            st.plotly_chart(fig, use_container_width=True)

        st.info("Run inference to overlay the posterior.")

with tab_posterior:
    if result is not None:
        st.plotly_chart(plot_joint(result), use_container_width=True)
    else:
        st.info("Set parameters in the sidebar and click **Run inference**.")
