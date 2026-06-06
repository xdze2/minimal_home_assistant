<script>
	import { onMount, onDestroy } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';

	const API = 'http://localhost:8001';

	// ── props (bound from parent) ─────────────────────────────────────────────
	let {
		model,
		inputs = $bindable({}),
		range  = $bindable({ start: '', end: '' }),
		solver = $bindable('zoh'),
	} = $props();

	// ── boundary/source nodes ─────────────────────────────────────────────────
	const inputNodes = $derived(
		(model?.nodes ?? []).filter((n) => n.kind === 'boundary' || n.kind === 'source')
	);

	// ── signal autocomplete ───────────────────────────────────────────────────
	let signals      = $state([]);
	let signalsError = $state(false);

	async function loadSignals() {
		try {
			const res = await fetch(`${API}/signals`);
			if (!res.ok) throw new Error(res.statusText);
			signals      = await res.json();
			signalsError = false;
		} catch {
			signalsError = true;
		}
	}

	function setInput(nodeId, value) {
		inputs = { ...inputs, [nodeId]: value };
	}

	// ── inline signal preview ─────────────────────────────────────────────────
	let previewNodeId  = $state(null);
	let previewLoading = $state(false);
	let previewError   = $state(null);
	let previewData    = $state(null);
	let previewMeta    = $state(null);

	async function previewSignal(nodeId) {
		const signal = inputs[nodeId];
		if (!signal?.trim()) return;
		if (previewNodeId === nodeId) { previewNodeId = null; return; } // toggle off
		previewNodeId  = nodeId;
		previewLoading = true;
		previewError   = null;
		previewData    = null;
		previewMeta    = null;
		try {
			const params = new URLSearchParams({ signal, start: range.start, end: range.end });
			const res    = await fetch(`${API}/series?${params}`);
			if (!res.ok) {
				const d = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(d.detail ?? res.statusText);
			}
			const data  = await res.json();
			previewData = data;
			previewMeta = computeMeta(data);
		} catch (e) {
			previewError = e.message;
		} finally {
			previewLoading = false;
		}
	}

	function computeMeta(data) {
		const values = data.values;
		const valid  = values.filter((v) => v !== null);
		if (valid.length === 0)
			return { count: 0, total: values.length, gaps: 0, min: null, max: null, mean: null };
		let gaps = 0, inGap = false;
		for (const v of values) {
			if (v === null) { if (!inGap) { gaps++; inGap = true; } } else { inGap = false; }
		}
		const sum = valid.reduce((a, b) => a + b, 0);
		return {
			count: valid.length, total: values.length, gaps,
			min: Math.min(...valid), max: Math.max(...valid), mean: sum / valid.length,
		};
	}

	function fmt(v) { return v === null || v === undefined ? '—' : v.toFixed(2); }

	// ── uPlot preview chart ───────────────────────────────────────────────────
	let chartContainer = $state(null);
	let uplot          = null;

	function destroyChart() {
		if (uplot) { uplot.destroy(); uplot = null; }
	}

	function buildChart(data) {
		destroyChart();
		if (!chartContainer || !data) return;
		const ts = data.t.map((s) => Date.parse(s) / 1000);
		const vs = data.values.map((v) => (v === null ? NaN : v));
		uplot = new uPlot({
			width: chartContainer.clientWidth || 700, height: 200,
			cursor: { show: true }, scales: { x: { time: true } },
			series: [
				{},
				{ label: data.signal, stroke: '#38bdf8', width: 1.5, spanGaps: false },
			],
			axes: [
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#1e293b' } },
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#334155' } },
			],
		}, [ts, vs], chartContainer);
	}

	$effect(() => { if (previewData) buildChart(previewData); });

	let resizeObserver;
	$effect(() => {
		if (!chartContainer) return;
		resizeObserver = new ResizeObserver(() => {
			if (uplot && chartContainer)
				uplot.setSize({ width: chartContainer.clientWidth, height: 200 });
		});
		resizeObserver.observe(chartContainer);
		return () => resizeObserver?.disconnect();
	});

	onMount(loadSignals);
	onDestroy(destroyChart);
</script>

<div class="inputs-panel">
	<!-- date range -->
	<div class="section-header">Date range</div>
	<div class="date-row">
		<label>
			<span>From</span>
			<input type="date" bind:value={range.start} />
		</label>
		<label>
			<span>To</span>
			<input type="date" bind:value={range.end} />
		</label>
	</div>

	<!-- solver -->
	<div class="section-header">Solver</div>
	<div class="solver-radios">
		<label class="radio-label">
			<input type="radio" bind:group={solver} value="ivp" />
			<span>IVP (BDF)</span>
		</label>
		<label class="radio-label">
			<input type="radio" bind:group={solver} value="zoh" />
			<span>ZOH</span>
		</label>
	</div>

	<!-- signal assignment -->
	<div class="section-header">
		Inputs
		{#if signalsError}<span class="sig-warn" title="Cannot reach API">⚠</span>{/if}
	</div>

	{#if !model}
		<p class="hint">No study loaded.</p>
	{:else if inputNodes.length === 0}
		<p class="hint">No boundary or source nodes in this model.</p>
	{:else}
		<datalist id="signal-list-inputs">
			{#each signals as s}<option value={s}></option>{/each}
		</datalist>

		<div class="node-rows">
			{#each inputNodes as node}
				{@const isOpen = previewNodeId === node.id}
				<div class="node-block" class:expanded={isOpen}>
					<div class="node-row">
						<div class="node-label">
							<span class="kind-dot kind-{node.kind}"></span>
							<span class="node-name">{node.label ?? node.id}</span>
							<span class="node-id">{node.id}</span>
						</div>
						<div class="node-input-row">
							<input
								type="text"
								list="signal-list-inputs"
								placeholder="measurement/field?tag=val"
								value={inputs[node.id] ?? ''}
								oninput={(e) => setInput(node.id, e.target.value)}
							/>
							<button
								class="preview-btn"
								class:active={isOpen}
								title={isOpen ? 'Hide preview' : 'Preview signal'}
								disabled={!inputs[node.id]?.trim() || !range.start || !range.end}
								onclick={() => previewSignal(node.id)}
							>▾</button>
						</div>
					</div>

					{#if isOpen}
						<div class="preview-block">
							{#if previewLoading}
								<div class="preview-status">Loading…</div>
							{:else if previewError}
								<div class="preview-status error">⚠ {previewError}</div>
							{:else if previewData}
								{#if previewMeta}
									<div class="meta-row">
										<span>{previewMeta.count} / {previewMeta.total} samples</span>
										{#if previewMeta.gaps > 0}
											<span class="gap-warn">{previewMeta.gaps} gap{previewMeta.gaps > 1 ? 's' : ''}</span>
										{/if}
										<span>min {fmt(previewMeta.min)} · max {fmt(previewMeta.max)} · mean {fmt(previewMeta.mean)}</span>
									</div>
								{/if}
								<div class="chart-wrap" bind:this={chartContainer}></div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.inputs-panel {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 16px 20px;
		overflow-y: auto;
		color: #f1f5f9;
	}

	.section-header {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #94a3b8;
		margin-top: 10px;
		margin-bottom: 2px;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.section-header:first-child { margin-top: 0; }

	.sig-warn { color: #f59e0b; font-size: 11px; }

	.date-row { display: flex; gap: 16px; }

	label {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	label > span {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #94a3b8;
	}

	input[type='date'],
	input[type='text'] {
		background: #0f172a;
		color: #e2e8f0;
		border: 1px solid #334155;
		border-radius: 4px;
		padding: 4px 8px;
		font-size: 12px;
		font-family: monospace;
		box-sizing: border-box;
		color-scheme: dark;
	}
	input:focus { outline: none; border-color: #6366f1; }

	.solver-radios { display: flex; gap: 14px; }

	.radio-label {
		display: flex;
		flex-direction: row;
		align-items: center;
		gap: 5px;
		cursor: pointer;
	}
	.radio-label span {
		font-size: 12px;
		color: #e2e8f0;
		text-transform: none;
		letter-spacing: normal;
	}

	.hint { font-size: 12px; color: #94a3b8; margin: 0; }

	/* node blocks */
	.node-rows { display: flex; flex-direction: column; gap: 8px; }

	.node-block {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		overflow: hidden;
	}
	.node-block.expanded { border-color: #94a3b8; }

	.node-row { padding: 10px 12px; display: flex; flex-direction: column; gap: 6px; }

	.node-label { display: flex; align-items: center; gap: 5px; }

	.kind-dot {
		width: 7px; height: 7px;
		border-radius: 50%; flex-shrink: 0;
	}
	.kind-dot.kind-boundary { background: #4ade80; }
	.kind-dot.kind-source   { background: #fbbf24; }

	.node-name {
		font-size: 12px; color: #e2e8f0; font-weight: 500;
		flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.node-id { font-size: 10px; font-family: monospace; color: #94a3b8; flex-shrink: 0; }

	.node-input-row { display: flex; gap: 6px; align-items: center; }
	.node-input-row input[type='text'] { flex: 1; }

	.preview-btn {
		background: #0f172a;
		border: 1px solid #334155;
		color: #94a3b8;
		border-radius: 4px;
		padding: 3px 8px;
		font-size: 14px;
		cursor: pointer;
		flex-shrink: 0;
		line-height: 1;
		transition: color 0.1s, background 0.1s;
	}
	.preview-btn:hover:not(:disabled) { color: #f1f5f9; background: #1e293b; }
	.preview-btn.active { color: #38bdf8; border-color: #38bdf8; }
	.preview-btn:disabled { opacity: 0.3; cursor: default; }

	.preview-block {
		border-top: 1px solid #334155;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.preview-status { font-size: 12px; color: #94a3b8; }
	.preview-status.error { color: #f87171; }

	.meta-row {
		display: flex;
		gap: 16px;
		flex-wrap: wrap;
		font-size: 11px;
		color: #94a3b8;
	}
	.gap-warn { color: #fbbf24; }

	.chart-wrap { flex-shrink: 0; }

	:global(.uplot)          { color: #94a3b8; }
	:global(.uplot canvas)   { background: #0f172a; }
	:global(.uplot .u-legend){ background: transparent; color: #94a3b8; font-size: 12px; }
</style>
