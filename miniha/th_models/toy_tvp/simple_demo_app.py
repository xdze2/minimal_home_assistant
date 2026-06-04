"""
Streamlit demo: a + b + c = 0
Observe a with noise; infer b and c given a mixture-of-Gaussians prior on b.
"""

import os
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

os.environ.setdefault("CMDSTAN_HOME", os.path.expanduser("~/.cmdstan"))

# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _get_model():
    from cmdstanpy import CmdStanModel
    stan_file = os.path.join(os.path.dirname(__file__), "simple_demo.stan")
    return CmdStanModel(stan_file=stan_file)


def run_inference(
    a_obs: np.ndarray,
    sigma_obs: float,
    b_mix_mu: list[float],
    b_mix_sigma: list[float],
    b_mix_weights: list[float],
    c_mu: float,
    c_sigma: float,
    chains: int = 4,
    iter_sampling: int = 1000,
    iter_warmup: int = 500,
    seed: int = 0,
):
    import arviz as az

    K = len(b_mix_mu)
    weights = np.array(b_mix_weights, dtype=float)
    weights /= weights.sum()

    data = {
        "n_obs": len(a_obs),
        "a_obs": a_obs.tolist(),
        "sigma_obs": sigma_obs,
        "K": K,
        "b_mix_mu": b_mix_mu,
        "b_mix_sigma": b_mix_sigma,
        "b_mix_weights": weights.tolist(),
        "c_mu": c_mu,
        "c_sigma": c_sigma,
    }

    model = _get_model()
    fit = model.sample(
        data=data,
        chains=chains,
        iter_sampling=iter_sampling,
        iter_warmup=iter_warmup,
        seed=seed,
        show_progress=False,
        show_console=False,
    )
    return az.from_cmdstanpy(fit)


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

def _prior_b_pdf(x: np.ndarray, mus, sigmas, weights) -> np.ndarray:
    w = np.array(weights, dtype=float)
    w /= w.sum()
    pdf = np.zeros_like(x, dtype=float)
    for mu, sigma, wi in zip(mus, sigmas, w):
        pdf += wi * np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    return pdf


def plot_prior_b(mus, sigmas, weights) -> go.Figure:
    x_min = min(mus) - 4 * max(sigmas)
    x_max = max(mus) + 4 * max(sigmas)
    x = np.linspace(x_min, x_max, 400)
    pdf = _prior_b_pdf(x, mus, sigmas, weights)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=pdf, mode="lines", name="prior(b)", line=dict(color="steelblue")))
    fig.update_layout(
        title="Prior on b",
        xaxis_title="b",
        yaxis_title="density",
        height=250,
        margin=dict(t=40, b=30),
    )
    return fig


def plot_posterior(idata, b_true: float | None, c_true: float | None) -> go.Figure:
    import arviz as az

    b_samples = idata.posterior["b"].values.flatten()
    c_samples = idata.posterior["c"].values.flatten()

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["Joint posterior (b, c)", "Marginals"],
    )

    # scatter
    idx = np.random.choice(len(b_samples), size=min(2000, len(b_samples)), replace=False)
    fig.add_trace(
        go.Scatter(
            x=b_samples[idx], y=c_samples[idx],
            mode="markers",
            marker=dict(size=3, color="steelblue", opacity=0.3),
            name="samples",
        ),
        row=1, col=1,
    )
    if b_true is not None and c_true is not None:
        fig.add_trace(
            go.Scatter(
                x=[b_true], y=[c_true],
                mode="markers",
                marker=dict(size=12, color="red", symbol="x"),
                name="true (b,c)",
            ),
            row=1, col=1,
        )

    # marginals as KDE approximation via histogram
    fig.add_trace(
        go.Histogram(
            x=b_samples, name="posterior b",
            histnorm="probability density",
            marker_color="steelblue", opacity=0.6,
            nbinsx=50,
        ),
        row=1, col=2,
    )
    fig.add_trace(
        go.Histogram(
            x=c_samples, name="posterior c",
            histnorm="probability density",
            marker_color="orange", opacity=0.6,
            nbinsx=50,
        ),
        row=1, col=2,
    )

    fig.update_xaxes(title_text="b", row=1, col=1)
    fig.update_yaxes(title_text="c", row=1, col=1)
    fig.update_xaxes(title_text="value", row=1, col=2)
    fig.update_yaxes(title_text="density", row=1, col=2)
    fig.update_layout(height=400, margin=dict(t=50, b=30), barmode="overlay")
    return fig


def plot_observations(a_obs: np.ndarray, a_true: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=a_obs, nbinsx=30, histnorm="probability density",
        name="observed a", marker_color="steelblue", opacity=0.7,
    ))
    fig.add_vline(x=a_true, line_dash="dash", line_color="red", annotation_text=f"true a = {a_true:.2f}")
    fig.update_layout(title="Observed values of a", xaxis_title="a", yaxis_title="density", height=250, margin=dict(t=40, b=30))
    return fig


def _gaussian_pdf(x, mu, sigma):
    return np.exp(-0.5 * ((x - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))


def plot_marginal_a(a_obs: np.ndarray, a_true: float, x_range: tuple) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=a_obs, nbinsx=30, histnorm="probability density",
        name="observed a", marker_color="steelblue", opacity=0.7,
    ))
    fig.add_vline(x=a_true, line_dash="dash", line_color="red",
                  annotation_text=f"true a = {a_true:.2f}")
    fig.update_layout(title="a  (observed)", xaxis_title="a", yaxis_title="density",
                      height=280, margin=dict(t=40, b=20),
                      xaxis=dict(range=x_range))
    return fig


# Distinct colours for up to 16 chains
_CHAIN_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    "#aec7e8", "#ffbb78", "#98df8a", "#ff9896", "#c5b0d5", "#c49c94",
]


def _add_chain_histograms(fig, samples_by_chain, nbinsx, x_range):
    """Add one semi-transparent histogram per chain, coloured distinctly."""
    n_chains = samples_by_chain.shape[0]
    for i, chain_samples in enumerate(samples_by_chain):
        fig.add_trace(go.Histogram(
            x=chain_samples,
            histnorm="probability density",
            nbinsx=nbinsx,
            name=f"chain {i+1}",
            marker_color=_CHAIN_COLORS[i % len(_CHAIN_COLORS)],
            opacity=0.45,
            xbins=dict(start=x_range[0], end=x_range[1],
                       size=(x_range[1] - x_range[0]) / nbinsx),
        ))


def plot_marginal_b(
    idata, b_true: float,
    mus, sigmas, weights,
    x_range: tuple,
) -> go.Figure:
    # shape: (chain, draw)
    b_by_chain = idata.posterior["b"].values

    x = np.linspace(x_range[0], x_range[1], 400)
    prior_pdf = _prior_b_pdf(x, mus, sigmas, weights)

    fig = go.Figure()
    _add_chain_histograms(fig, b_by_chain, nbinsx=60, x_range=x_range)
    fig.add_trace(go.Scatter(
        x=x, y=prior_pdf, mode="lines", name="prior",
        line=dict(color="orange", width=2.5),
    ))
    fig.add_vline(x=b_true, line_dash="dash", line_color="red",
                  annotation_text=f"true b = {b_true:.2f}")
    fig.update_layout(
        title="b  (prior + posterior per chain)", xaxis_title="b", yaxis_title="density",
        height=300, margin=dict(t=40, b=20), barmode="overlay",
        legend=dict(orientation="h", y=1.15),
        xaxis=dict(range=x_range),
    )
    return fig


def plot_marginal_c(idata, c_true: float, c_mu: float, c_sigma: float, x_range: tuple) -> go.Figure:
    c_by_chain = idata.posterior["c"].values

    x = np.linspace(x_range[0], x_range[1], 400)
    prior_pdf = _gaussian_pdf(x, c_mu, c_sigma)

    fig = go.Figure()
    _add_chain_histograms(fig, c_by_chain, nbinsx=60, x_range=x_range)
    fig.add_trace(go.Scatter(
        x=x, y=prior_pdf, mode="lines", name="prior",
        line=dict(color="orange", width=2.5),
    ))
    fig.add_vline(x=c_true, line_dash="dash", line_color="red",
                  annotation_text=f"true c = {c_true:.2f}")
    fig.update_layout(
        title="c  (prior + posterior per chain)", xaxis_title="c", yaxis_title="density",
        height=300, margin=dict(t=40, b=20), barmode="overlay",
        legend=dict(orientation="h", y=1.15),
        xaxis=dict(range=x_range),
    )
    return fig


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Simple Bayes demo: a+b+c=0", layout="wide")
st.title("Simple Bayesian demo: a + b + c = 0")
st.caption("Observe _a_ with noise. Infer _b_ and _c_ given priors. Prior on _b_ is a mixture of Gaussians.")

# --- Sidebar ---
with st.sidebar:
    st.header("Ground truth")
    b_true = st.number_input("True b", value=1.5, step=0.1)
    c_true = st.number_input("True c", value=0.5, step=0.1)
    a_true = -(b_true + c_true)
    st.metric("True a = -(b+c)", f"{a_true:.3f}")

    st.header("Observations")
    n_obs = st.slider("Number of observations", 5, 500, 100)
    sigma_obs = st.slider("Observation noise σ", 0.01, 5.0, 0.3, step=0.01)
    obs_seed = st.number_input("Data seed", value=42, step=1)

    st.header("Prior on c (Gaussian)")
    c_mu = st.number_input("c prior mean", value=0.0, step=0.1)
    c_sigma = st.number_input("c prior std", value=2.0, min_value=0.01, step=0.1)

    st.header("Prior on b (mixture of Gaussians)")

    # Session state for mixture components
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

    st.header("Sampler")
    chains = st.selectbox("Chains", [1, 2, 4, 8, 16], index=1)
    iter_sampling = st.select_slider("Sampling iterations", [200, 500, 1000, 2000], value=1000)
    iter_warmup = st.select_slider("Warmup iterations", [200, 500, 1000], value=500)
    mcmc_seed = st.number_input("MCMC seed", value=0, step=1)

    run_button = st.button("Run inference", type="primary")

# --- Generate data ---
rng = np.random.default_rng(int(obs_seed))
a_obs = rng.normal(loc=a_true, scale=sigma_obs, size=n_obs)

b_mix_mu = [c["mu"] for c in components]
b_mix_sigma = [c["sigma"] for c in components]
b_mix_weights = [c["weight"] for c in components]

# --- Main area ---
tab_data, tab_prior, tab_posterior, tab_marginals = st.tabs(["Data", "Prior on b", "Posterior", "Marginals"])

with tab_data:
    st.plotly_chart(plot_observations(a_obs, a_true), use_container_width=True)
    st.write(f"Mean of observations: **{a_obs.mean():.3f}** (true: {a_true:.3f}), std: **{a_obs.std():.3f}**")

with tab_prior:
    st.plotly_chart(plot_prior_b(b_mix_mu, b_mix_sigma, b_mix_weights), use_container_width=True)

with tab_posterior:
    if run_button:
        with st.spinner("Sampling with Stan..."):
            try:
                idata = run_inference(
                    a_obs=a_obs,
                    sigma_obs=sigma_obs,
                    b_mix_mu=b_mix_mu,
                    b_mix_sigma=b_mix_sigma,
                    b_mix_weights=b_mix_weights,
                    c_mu=c_mu,
                    c_sigma=c_sigma,
                    chains=chains,
                    iter_sampling=iter_sampling,
                    iter_warmup=iter_warmup,
                    seed=int(mcmc_seed),
                )
                st.session_state["idata"] = idata
                st.session_state["b_true_used"] = b_true
                st.session_state["c_true_used"] = c_true
                st.success("Done!")
            except Exception as e:
                st.error(f"Stan error: {e}")

    if "idata" in st.session_state:
        idata = st.session_state["idata"]
        bt = st.session_state.get("b_true_used")
        ct = st.session_state.get("c_true_used")
        st.plotly_chart(plot_posterior(idata, bt, ct), use_container_width=True)

        import arviz as az
        summary = az.summary(idata, var_names=["b", "c"], round_to=3)
        st.dataframe(summary)
    else:
        st.info("Set parameters in the sidebar and click **Run inference**.")

with tab_marginals:
    if "idata" in st.session_state:
        idata = st.session_state["idata"]
        bt = st.session_state.get("b_true_used", b_true)
        ct = st.session_state.get("c_true_used", c_true)

        b_samples = idata.posterior["b"].values.flatten()
        c_samples = idata.posterior["c"].values.flatten()

        # shared x range: union of a_obs, b posterior+prior, c posterior+prior
        padding = max(sigma_obs, max(b_mix_sigma), c_sigma)
        x_min = min(
            a_obs.min(),
            b_samples.min(), min(b_mix_mu) - 3 * max(b_mix_sigma),
            c_samples.min(), c_mu - 3 * c_sigma,
        ) - padding
        x_max = max(
            a_obs.max(),
            b_samples.max(), max(b_mix_mu) + 3 * max(b_mix_sigma),
            c_samples.max(), c_mu + 3 * c_sigma,
        ) + padding
        x_range = (x_min, x_max)

        st.plotly_chart(plot_marginal_a(a_obs, a_true, x_range), use_container_width=True)
        st.plotly_chart(
            plot_marginal_b(idata, bt, b_mix_mu, b_mix_sigma, b_mix_weights, x_range),
            use_container_width=True,
        )
        st.plotly_chart(
            plot_marginal_c(idata, ct, c_mu, c_sigma, x_range),
            use_container_width=True,
        )
    else:
        st.info("Run inference first to see marginals.")
