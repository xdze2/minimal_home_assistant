<script>
	import { onMount, onDestroy } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';
	import { MODELS } from '$lib/models.js';

	const API = 'http://localhost:8001';

	// ── model picker ──────────────────────────────────────────────────────────
	let selectedModelId = $state(MODELS[0].id);
	let model = $state(structuredClone(MODELS[0].model));

	function onModelChange(e) {
		selectedModelId = e.target.value;
		const found = MODELS.find((m) => m.id === selectedModelId);
		if (found) {
			model = structuredClone(found.model);
			inputs = {};
			simResult = null;
			simError = null;
		}
	}

	// ── boundary/source nodes from current model ──────────────────────────────
	const inputNodes = $derived(
		(model.nodes ?? []).filter((n) => n.kind === 'boundary' || n.kind === 'source')
	);

	// ── signal autocomplete ───────────────────────────────────────────────────
	let signals = $state([]);
	let signalsError = $state(false);

	async function loadSignals() {
		try {
			const res = await fetch(`${API}/signals`);
			if (!res.ok) throw new Error(res.statusText);
			signals = await res.json();
			signalsError = false;
		} catch {
			signalsError = true;
		}
	}

	// ── date range ────────────────────────────────────────────────────────────
	function defaultDateRange() {
		const end = new Date();
		const start = new Date(end - 7 * 24 * 3600 * 1000);
		return {
			start: start.toISOString().slice(0, 16),
			end:   end.toISOString().slice(0, 16),
		};
	}

	let range = $state(defaultDateRange());

	// ── inputs map: node_id → signal_name ────────────────────────────────────
	let inputs = $state({});

	function setInput(nodeId, value) {
		inputs = { ...inputs, [nodeId]: value };
	}

	// ── fetch inputs ──────────────────────────────────────────────────────────
	let fetchLoading = $state(false);
	let fetchError = $state(null);
	let fetchResult = $state(null); // { node_id: { signal, t, values } }

	async function fetchInputs() {
		fetchLoading = true;
		fetchError = null;
		fetchResult = null;
		try {
			const body = {
				model,
				start: new Date(range.start).toISOString(),
				end:   new Date(range.end).toISOString(),
				inputs,
			};
			const res = await fetch(`${API}/simulate/inputs`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) {
				const detail = await res.json().catch(() => ({ detail: res.statusText }));
				const msg = detail?.detail?.message ?? detail?.detail ?? res.statusText;
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
	let simError = $state(null);
	let simResult = $state(null); // { t, nodes }

	async function runSimulation() {
		simLoading = true;
		simError = null;
		simResult = null;
		try {
			const body = {
				model,
				start: new Date(range.start).toISOString(),
				end:   new Date(range.end).toISOString(),
				inputs,
			};
			const res = await fetch(`${API}/simulate`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body),
			});
			if (!res.ok) {
				const detail = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(detail.detail ?? res.statusText);
			}
			simResult = await res.json();
		} catch (e) {
			simError = e.message;
		} finally {
			simLoading = false;
		}
	}

	// ── uPlot charts ──────────────────────────────────────────────────────────
	const SERIES_COLORS      = ['#38bdf8', '#fb923c', '#a78bfa', '#34d399', '#f472b6', '#facc15'];
	const INPUT_SERIES_COLORS = ['#4ade80', '#fbbf24', '#f472b6', '#c084fc', '#67e8f9', '#fdba74'];

	// inputs chart
	let inputsChartContainer = $state(null);
	let inputsUplot = null;

	function destroyInputsChart() {
		if (inputsUplot) { inputsUplot.destroy(); inputsUplot = null; }
	}

	function buildInputsChart(result) {
		destroyInputsChart();
		if (!inputsChartContainer || !result) return;

		const nodeIds = Object.keys(result);
		if (nodeIds.length === 0) return;

		const ts = result[nodeIds[0]].t.map((s) => Date.parse(s) / 1000);
		const data = [ts, ...nodeIds.map((id) => result[id].values.map((v) => (v === null ? NaN : v)))];

		const series = [
			{},
			...nodeIds.map((id, i) => ({
				label: result[id].signal,
				stroke: INPUT_SERIES_COLORS[i % INPUT_SERIES_COLORS.length],
				width: 1.5,
				spanGaps: false,
			})),
		];

		const opts = {
			width:  inputsChartContainer.clientWidth || 800,
			height: 220,
			cursor: { show: true },
			scales: { x: { time: true } },
			series,
			axes: [
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#1e293b' } },
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#334155' } },
			],
			legend: { show: true },
		};
		inputsUplot = new uPlot(opts, data, inputsChartContainer);
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

	// simulation results chart
	let chartContainer = $state(null);
	let uplot = null;

	function destroyChart() {
		if (uplot) { uplot.destroy(); uplot = null; }
	}

	function buildChart(result) {
		destroyChart();
		if (!chartContainer || !result) return;

		const ts = result.t.map((s) => Date.parse(s) / 1000);
		const massIds = Object.keys(result.nodes);

		const data = [ts, ...massIds.map((id) => result.nodes[id].map((v) => (v === null ? NaN : v)))];

		const series = [
			{},
			...massIds.map((id, i) => ({
				label: id,
				stroke: SERIES_COLORS[i % SERIES_COLORS.length],
				width: 1.5,
				spanGaps: false,
			})),
		];

		const opts = {
			width:  chartContainer.clientWidth || 800,
			height: 300,
			cursor: { show: true },
			scales: { x: { time: true } },
			series,
			axes: [
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#1e293b' } },
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#334155' }, label: '°C' },
			],
			legend: { show: true },
		};
		uplot = new uPlot(opts, data, chartContainer);
	}

	$effect(() => {
		if (simResult) buildChart(simResult);
	});

	let resizeObserver;
	$effect(() => {
		if (!chartContainer) return;
		resizeObserver = new ResizeObserver(() => {
			if (uplot && chartContainer) uplot.setSize({ width: chartContainer.clientWidth, height: 300 });
		});
		resizeObserver.observe(chartContainer);
		return () => resizeObserver?.disconnect();
	});

	onMount(loadSignals);
	onDestroy(() => { destroyInputsChart(); destroyChart(); });
</script>

<div class="sim-run">
	<!-- ── config panel ── -->
	<aside class="config-panel">
		<div class="section-header">Model</div>
		<select value={selectedModelId} onchange={onModelChange}>
			{#each MODELS as m}
				<option value={m.id}>{m.label}</option>
			{/each}
		</select>

		<div class="section-header">Date range</div>
		<label>
			<span>From</span>
			<input type="datetime-local" bind:value={range.start} />
		</label>
		<label>
			<span>To</span>
			<input type="datetime-local" bind:value={range.end} />
		</label>

		<div class="section-header">
			Inputs
			{#if signalsError}<span class="sig-warn" title="Cannot reach API">⚠</span>{/if}
		</div>

		{#if inputNodes.length === 0}
			<p class="hint">No boundary or source nodes in this model.</p>
		{:else}
			<div class="inputs-table">
				{#each inputNodes as node}
					<div class="input-row">
						<div class="node-label">
							<span class="kind-dot kind-{node.kind}"></span>
							<span class="node-name">{node.label ?? node.id}</span>
							<span class="node-id">{node.id}</span>
						</div>
						<input
							type="text"
							list="signal-list-sim"
							placeholder="measurement/field?tag=val"
							value={inputs[node.id] ?? ''}
							oninput={(e) => setInput(node.id, e.target.value)}
						/>
					</div>
				{/each}
			</div>
		{/if}

		<datalist id="signal-list-sim">
			{#each signals as s}
				<option value={s}></option>
			{/each}
		</datalist>

		<div class="action-btns">
			<button class="fetch-btn" onclick={fetchInputs} disabled={fetchLoading || simLoading}>
				{fetchLoading ? 'Fetching…' : 'Fetch inputs'}
			</button>
			<button class="run-btn" onclick={runSimulation} disabled={simLoading || fetchLoading}>
				{simLoading ? 'Running…' : 'Run simulation'}
			</button>
		</div>
	</aside>

	<!-- ── results pane ── -->
	<div class="results-pane">
		{#if !fetchResult && !fetchLoading && !fetchError && !simResult && !simLoading && !simError}
			<div class="empty">Configure inputs and click Fetch inputs</div>

		{:else}
			<!-- inputs section -->
			{#if fetchLoading}
				<div class="section-loading">Fetching input signals…</div>
			{:else if fetchError}
				<div class="error-box">⚠ {fetchError}</div>
			{:else if fetchResult}
				<div class="result-header">
					<span class="result-title">Inputs</span>
					<span class="result-meta">{Object.keys(fetchResult).length} signal{Object.keys(fetchResult).length !== 1 ? 's' : ''} · {fetchResult[Object.keys(fetchResult)[0]]?.t.length ?? 0} steps</span>
				</div>
				<div class="chart-wrap" bind:this={inputsChartContainer}></div>
			{/if}

			<!-- simulation section -->
			{#if simLoading}
				<div class="section-loading">Running simulation…</div>
			{:else if simError}
				<div class="error-box">⚠ {simError}</div>
			{:else if simResult}
				<div class="result-header">
					<span class="result-title">Temperature — mass nodes</span>
					<span class="result-meta">{Object.keys(simResult.nodes).length} node{Object.keys(simResult.nodes).length !== 1 ? 's' : ''} · {simResult.t.length} steps</span>
				</div>
				<div class="chart-wrap" bind:this={chartContainer}></div>
			{/if}
		{/if}
	</div>
</div>

<style>
	.sim-run {
		display: flex;
		flex: 1;
		min-height: 0;
		overflow: hidden;
	}

	/* ── config panel ── */
	.config-panel {
		width: 280px;
		flex-shrink: 0;
		background: #1e293b;
		border-right: 1px solid #334155;
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 14px 12px;
		overflow-y: auto;
	}

	.section-header {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #64748b;
		margin-top: 10px;
		margin-bottom: 2px;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.section-header:first-child { margin-top: 0; }

	.sig-warn { color: #f59e0b; font-size: 11px; }

	select {
		background: #0f172a;
		color: #f1f5f9;
		border: 1px solid #334155;
		border-radius: 4px;
		padding: 5px 8px;
		font-size: 13px;
		cursor: pointer;
		width: 100%;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	label > span {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #64748b;
	}

	input[type='datetime-local'],
	input[type='text'] {
		background: #0f172a;
		color: #e2e8f0;
		border: 1px solid #334155;
		border-radius: 4px;
		padding: 4px 8px;
		font-size: 12px;
		font-family: monospace;
		width: 100%;
		box-sizing: border-box;
		color-scheme: dark;
	}
	input:focus {
		outline: none;
		border-color: #6366f1;
	}

	/* ── inputs table ── */
	.inputs-table {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.input-row {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	.node-label {
		display: flex;
		align-items: center;
		gap: 5px;
	}

	.kind-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		flex-shrink: 0;
	}
	.kind-dot.kind-boundary { background: #4ade80; }
	.kind-dot.kind-source   { background: #fbbf24; }

	.node-name {
		font-size: 12px;
		color: #e2e8f0;
		font-weight: 500;
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.node-id {
		font-size: 10px;
		font-family: monospace;
		color: #475569;
		flex-shrink: 0;
	}

	.hint {
		font-size: 12px;
		color: #475569;
		margin: 0;
	}

	/* ── action buttons ── */
	.action-btns {
		margin-top: 14px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.fetch-btn {
		background: #0f4c75;
		color: #f1f5f9;
		border: 1px solid #1a6fa3;
		border-radius: 4px;
		padding: 7px 12px;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		width: 100%;
		transition: background 0.15s;
	}
	.fetch-btn:hover:not(:disabled) { background: #1a6fa3; }
	.fetch-btn:disabled { opacity: 0.5; cursor: not-allowed; }

	.run-btn {
		background: #4f46e5;
		color: #f1f5f9;
		border: none;
		border-radius: 4px;
		padding: 8px 12px;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		width: 100%;
		transition: background 0.15s;
	}
	.run-btn:hover:not(:disabled) { background: #4338ca; }
	.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }

	/* ── results pane ── */
	.results-pane {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		padding: 20px 24px;
		gap: 12px;
		overflow-y: auto;
	}

	.empty {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #475569;
		font-size: 14px;
	}

	.section-loading {
		font-size: 13px;
		color: #64748b;
		padding: 8px 0;
	}

	.error-box {
		background: #1c0a0a;
		border: 1px solid #7f1d1d;
		border-radius: 4px;
		color: #f87171;
		padding: 12px 16px;
		font-size: 13px;
	}

	.result-header {
		display: flex;
		align-items: baseline;
		gap: 12px;
	}

	.result-title {
		font-size: 14px;
		font-weight: 600;
		color: #f1f5f9;
	}

	.result-meta {
		font-size: 12px;
		color: #64748b;
	}

	.chart-wrap {
		flex-shrink: 0;
	}

	/* uPlot dark theme overrides */
	:global(.uplot) { color: #94a3b8; }
	:global(.uplot canvas) { background: #0f172a; }
	:global(.uplot .u-legend) { background: transparent; color: #94a3b8; font-size: 12px; }
</style>
