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

	// ── stale tracking ────────────────────────────────────────────────────────
	// snapshot of (range + inputs) at the time of the last successful preview
	let previewedSnapshot = $state(null);

	function currentSnapshot() {
		return JSON.stringify({ range, inputs });
	}

	const isStale = $derived(
		previewedSnapshot !== null && previewedSnapshot !== currentSnapshot()
	);

	// ── signal previews (one per node) ────────────────────────────────────────
	let previews    = $state({});
	let anyLoading  = $derived(Object.values(previews).some((p) => p.loading));

	async function previewAll() {
		const nodes = inputNodes.filter((n) => inputs[n.id]?.trim() && range.start && range.end);
		if (nodes.length === 0) return;

		// mark all as loading
		const loading = {};
		for (const n of nodes) loading[n.id] = { loading: true, error: null, data: null, meta: null };
		previews = loading;

		await Promise.all(nodes.map(async (node) => {
			try {
				const params = new URLSearchParams({ signal: inputs[node.id], start: range.start, end: range.end });
				const res    = await fetch(`${API}/series?${params}`);
				if (!res.ok) {
					const d = await res.json().catch(() => ({ detail: res.statusText }));
					throw new Error(d.detail ?? res.statusText);
				}
				const data = await res.json();
				previews = { ...previews, [node.id]: { loading: false, error: null, data, meta: computeMeta(data) } };
			} catch (e) {
				previews = { ...previews, [node.id]: { loading: false, error: e.message, data: null, meta: null } };
			}
		}));

		previewedSnapshot = currentSnapshot();
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

	// ── uPlot charts (one per node) ───────────────────────────────────────────
	let chartContainers = $state({});  // nodeId → DOM element
	const uplots = {};                 // nodeId → uPlot instance

	function buildChart(nodeId, el, data) {
		if (uplots[nodeId]) { uplots[nodeId].destroy(); delete uplots[nodeId]; }
		if (!el || !data) return;
		const ts = data.t.map((s) => Date.parse(s) / 1000);
		const vs = data.values.map((v) => (v === null ? NaN : v));
		uplots[nodeId] = new uPlot({
			width: el.clientWidth || 700, height: 180,
			cursor: { show: true }, scales: { x: { time: true } },
			series: [
				{},
				{ label: data.signal, stroke: '#38bdf8', width: 1.5, spanGaps: false },
			],
			axes: [
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#1e293b' } },
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#334155' } },
			],
		}, [ts, vs], el);
	}

	$effect(() => {
		for (const [nodeId, el] of Object.entries(chartContainers)) {
			const p = previews[nodeId];
			if (el && p?.data) buildChart(nodeId, el, p.data);
		}
	});

	const canPreview = $derived(
		range.start && range.end && inputNodes.some((n) => inputs[n.id]?.trim())
	);

	onMount(loadSignals);
	onDestroy(() => { for (const u of Object.values(uplots)) u.destroy(); });
</script>

<div class="inputs-panel">
	<!-- date range + preview button -->
	<div class="top-bar">
		<div>
			<div class="section-header" style="margin-top:0">Date range</div>
			<div class="date-row">
				<label>
					<span>From</span>
					<input type="date" bind:value={range.start} class:missing={!range.start} />
				</label>
				<label>
					<span>To</span>
					<input type="date" bind:value={range.end} class:missing={!range.end} />
				</label>
			</div>
		</div>

		<button
			class="preview-all-btn"
			class:stale={isStale}
			disabled={!canPreview || anyLoading}
			onclick={previewAll}
		>
			{anyLoading ? 'Loading…' : isStale ? 'Preview ●' : 'Preview'}
		</button>
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
				{@const p = previews[node.id]}
				<div class="node-block">
					<div class="node-row">
						<div class="node-label">
							<span class="kind-dot kind-{node.kind}"></span>
							<span class="node-name">{node.label ?? node.id}</span>
							<span class="node-id">{node.id}</span>
						</div>
						<input
							type="text"
							list="signal-list-inputs"
							placeholder="measurement/field?tag=val"
							value={inputs[node.id] ?? ''}
							class:missing={!inputs[node.id]?.trim()}
							oninput={(e) => setInput(node.id, e.target.value)}
						/>
					</div>

					{#if p}
						<div class="preview-block">
							{#if p.loading}
								<div class="preview-status">Loading…</div>
							{:else if p.error}
								<div class="preview-status error">⚠ {p.error}</div>
							{:else if p.data}
								{#if p.meta}
									<div class="meta-row">
										<span>{p.meta.count} / {p.meta.total} samples</span>
										{#if p.meta.gaps > 0}
											<span class="gap-warn">{p.meta.gaps} gap{p.meta.gaps > 1 ? 's' : ''}</span>
										{/if}
										<span>min {fmt(p.meta.min)} · max {fmt(p.meta.max)} · mean {fmt(p.meta.mean)}</span>
									</div>
								{/if}
								<div class="chart-wrap" bind:this={chartContainers[node.id]}></div>
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

	.top-bar {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 16px;
		margin-bottom: 4px;
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
	input.missing { border-color: #7f1d1d; color: #f87171; }
	input.missing::placeholder { color: #f87171; opacity: 0.5; }

	.preview-all-btn {
		background: #0f172a;
		border: 1px solid #334155;
		color: #94a3b8;
		border-radius: 4px;
		padding: 6px 14px;
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
		flex-shrink: 0;
		transition: color 0.1s, border-color 0.1s, background 0.1s;
		white-space: nowrap;
	}
	.preview-all-btn:hover:not(:disabled) { color: #f1f5f9; background: #1e293b; }
	.preview-all-btn:disabled { opacity: 0.3; cursor: not-allowed; }
	.preview-all-btn.stale { color: #fbbf24; border-color: #92400e; }
	.preview-all-btn.stale:hover:not(:disabled) { background: #1c1007; }

	.hint { font-size: 12px; color: #94a3b8; margin: 0; }

	/* node blocks */
	.node-rows { display: flex; flex-direction: column; gap: 8px; }

	.node-block {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		overflow: hidden;
	}

	.node-row {
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

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
