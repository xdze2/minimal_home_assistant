<script>
	import { onMount, onDestroy } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';

	const API = 'http://localhost:8001';

	// ── props (read-only — config lives in InputsPanel) ───────────────────────
	let { model, inputs = {}, range = { start: '', end: '' }, solver = 'zoh' } = $props();

	// ── fetch inputs ──────────────────────────────────────────────────────────
	let fetchLoading = $state(false);
	let fetchError   = $state(null);
	let fetchResult  = $state(null);

	async function fetchInputs() {
		fetchLoading = true;
		fetchError   = null;
		fetchResult  = null;
		try {
			const body = { model, start: range.start, end: range.end, inputs };
			const res  = await fetch(`${API}/simulate/inputs`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) {
				const d   = await res.json().catch(() => ({ detail: res.statusText }));
				const msg = d?.detail?.message ?? d?.detail ?? res.statusText;
				throw new Error(msg);
			}
			fetchResult = await res.json();
		} catch (e) {
			fetchError = e.message;
		} finally {
			fetchLoading = false;
		}
	}

	// ── simulation ────────────────────────────────────────────────────────────
	let simLoading = $state(false);
	let simError   = $state(null);
	let simResult  = $state(null);

	async function runSimulation() {
		simLoading = true;
		simError   = null;
		simResult  = null;
		try {
			const body = { model, start: range.start, end: range.end, inputs, solver };
			const res  = await fetch(`${API}/simulate/run`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(d.detail ?? res.statusText);
			}
			simResult = await res.json();
		} catch (e) {
			simError = e.message;
		} finally {
			simLoading = false;
		}
	}

	// ── uPlot charts ──────────────────────────────────────────────────────────
	const SERIES_COLORS       = ['#38bdf8', '#fb923c', '#a78bfa', '#34d399', '#f472b6', '#facc15'];
	const INPUT_SERIES_COLORS = ['#4ade80', '#fbbf24', '#f472b6', '#c084fc', '#67e8f9', '#fdba74'];

	let inputsChartContainer = $state(null);
	let inputsUplot          = null;

	function destroyInputsChart() {
		if (inputsUplot) { inputsUplot.destroy(); inputsUplot = null; }
	}

	function buildInputsChart(result) {
		destroyInputsChart();
		if (!inputsChartContainer || !result) return;
		const nodeIds = Object.keys(result);
		if (nodeIds.length === 0) return;
		const ts   = result[nodeIds[0]].t.map((s) => Date.parse(s) / 1000);
		const data = [ts, ...nodeIds.map((id) => result[id].values.map((v) => (v === null ? NaN : v)))];
		const series = [{}, ...nodeIds.map((id, i) => ({
			label: result[id].signal,
			stroke: INPUT_SERIES_COLORS[i % INPUT_SERIES_COLORS.length],
			width: 1.5, spanGaps: false,
		}))];
		inputsUplot = new uPlot({
			width: inputsChartContainer.clientWidth || 800, height: 220,
			cursor: { show: true }, scales: { x: { time: true } }, series,
			axes: [
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#1e293b' } },
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#334155' } },
			],
			legend: { show: true },
		}, data, inputsChartContainer);
	}

	$effect(() => { if (fetchResult) buildInputsChart(fetchResult); });

	let inputsResizeObserver;
	$effect(() => {
		if (!inputsChartContainer) return;
		inputsResizeObserver = new ResizeObserver(() => {
			if (inputsUplot && inputsChartContainer)
				inputsUplot.setSize({ width: inputsChartContainer.clientWidth, height: 220 });
		});
		inputsResizeObserver.observe(inputsChartContainer);
		return () => inputsResizeObserver?.disconnect();
	});

	let chartContainer = $state(null);
	let uplot          = null;

	function destroyChart() {
		if (uplot) { uplot.destroy(); uplot = null; }
	}

	function buildChart(result) {
		destroyChart();
		if (!chartContainer || !result) return;
		const ts      = result.t.map((s) => Date.parse(s) / 1000);
		const massIds = Object.keys(result.nodes);
		const data    = [ts, ...massIds.map((id) => result.nodes[id].map((v) => (v === null ? NaN : v)))];
		const series  = [{}, ...massIds.map((id, i) => ({
			label: id,
			stroke: SERIES_COLORS[i % SERIES_COLORS.length],
			width: 1.5, spanGaps: false,
		}))];
		uplot = new uPlot({
			width: chartContainer.clientWidth || 800, height: 300,
			cursor: { show: true }, scales: { x: { time: true } }, series,
			axes: [
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#1e293b' } },
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#334155' }, label: '°C' },
			],
			legend: { show: true },
		}, data, chartContainer);
	}

	$effect(() => { if (simResult) buildChart(simResult); });

	let resizeObserver;
	$effect(() => {
		if (!chartContainer) return;
		resizeObserver = new ResizeObserver(() => {
			if (uplot && chartContainer) uplot.setSize({ width: chartContainer.clientWidth, height: 300 });
		});
		resizeObserver.observe(chartContainer);
		return () => resizeObserver?.disconnect();
	});

	onDestroy(() => { destroyInputsChart(); destroyChart(); });
</script>

<div class="run-panel">
	<!-- action bar -->
	<div class="action-bar">
		<button class="fetch-btn" onclick={fetchInputs} disabled={fetchLoading || simLoading}>
			{fetchLoading ? 'Fetching…' : 'Fetch inputs'}
		</button>
		<button class="run-btn" onclick={runSimulation} disabled={simLoading || fetchLoading}>
			{simLoading ? 'Running…' : 'Run simulation'}
		</button>
		<span class="solver-badge">{solver}</span>
	</div>

	<!-- results -->
	<div class="results">
		{#if !fetchResult && !fetchLoading && !fetchError && !simResult && !simLoading && !simError}
			<div class="empty">Configure inputs in the Inputs step, then click Fetch or Run.</div>

		{:else}
			{#if fetchLoading}
				<div class="status-msg">Fetching input signals…</div>
			{:else if fetchError}
				<div class="error-box">⚠ {fetchError}</div>
			{:else if fetchResult}
				<div class="result-header">
					<span class="result-title">Inputs</span>
					<span class="result-meta">
						{Object.keys(fetchResult).length} signal{Object.keys(fetchResult).length !== 1 ? 's' : ''}
						· {fetchResult[Object.keys(fetchResult)[0]]?.t.length ?? 0} steps
					</span>
				</div>
				<div class="chart-wrap" bind:this={inputsChartContainer}></div>
			{/if}

			{#if simLoading}
				<div class="status-msg">Running simulation…</div>
			{:else if simError}
				<div class="error-box">⚠ {simError}</div>
			{:else if simResult}
				<div class="result-header">
					<span class="result-title">Temperature — mass nodes</span>
					<span class="result-meta">
						{Object.keys(simResult.nodes).length} node{Object.keys(simResult.nodes).length !== 1 ? 's' : ''}
						· {simResult.t.length} steps
						{#if simResult.meta}· {simResult.meta.elapsed_s.toFixed(2)} s · solver: {simResult.meta.solver}{/if}
					</span>
				</div>
				{#if simResult.meta}
					<div class="meta-block">
						<span>n_rhs_evals: {simResult.meta.n_rhs_evals ?? '—'}</span>
						<span>n_steps: {simResult.meta.n_steps ?? '—'}</span>
						<span class:ok={simResult.meta.success} class:fail={!simResult.meta.success}>
							{simResult.meta.success ? '✓ success' : '✗ ' + simResult.meta.message}
						</span>
					</div>
				{/if}
				<div class="chart-wrap" bind:this={chartContainer}></div>
			{/if}
		{/if}
	</div>
</div>

<style>
	.run-panel {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
	}

	.action-bar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 12px 20px;
		background: #1e293b;
		border-bottom: 1px solid #334155;
		flex-shrink: 0;
	}

	.solver-badge {
		font-size: 11px;
		font-family: monospace;
		color: #94a3b8;
		margin-left: 4px;
	}

	.fetch-btn {
		background: #0f4c75; color: #f1f5f9;
		border: 1px solid #1a6fa3; border-radius: 4px;
		padding: 7px 16px; font-size: 13px; font-weight: 600;
		cursor: pointer; transition: background 0.15s;
	}
	.fetch-btn:hover:not(:disabled) { background: #1a6fa3; }
	.fetch-btn:disabled { opacity: 0.5; cursor: not-allowed; }

	.run-btn {
		background: #4f46e5; color: #f1f5f9;
		border: none; border-radius: 4px;
		padding: 8px 16px; font-size: 13px; font-weight: 600;
		cursor: pointer; transition: background 0.15s;
	}
	.run-btn:hover:not(:disabled) { background: #4338ca; }
	.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }

	.results {
		flex: 1;
		display: flex;
		flex-direction: column;
		padding: 20px 24px;
		gap: 12px;
		overflow-y: auto;
		min-height: 0;
	}

	.empty {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #94a3b8;
		font-size: 14px;
	}

	.status-msg { font-size: 13px; color: #94a3b8; padding: 8px 0; }

	.error-box {
		background: #1c0a0a; border: 1px solid #7f1d1d;
		border-radius: 4px; color: #f87171; padding: 12px 16px; font-size: 13px;
	}

	.result-header { display: flex; align-items: baseline; gap: 12px; }
	.result-title  { font-size: 14px; font-weight: 600; color: #f1f5f9; }
	.result-meta   { font-size: 12px; color: #94a3b8; }

	.meta-block {
		display: flex; gap: 16px; font-size: 11px; font-family: monospace;
		color: #94a3b8; padding: 4px 0;
	}
	.meta-block .ok   { color: #4ade80; }
	.meta-block .fail { color: #f87171; }

	.chart-wrap { flex-shrink: 0; }

	:global(.uplot)          { color: #94a3b8; }
	:global(.uplot canvas)   { background: #0f172a; }
	:global(.uplot .u-legend){ background: transparent; color: #94a3b8; font-size: 12px; }
</style>
