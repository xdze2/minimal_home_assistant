<script>
	import { onMount, onDestroy } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';

	const API = 'http://localhost:8001';

	// ── signal list ───────────────────────────────────────────────────────────
	let signals = $state([]);
	let signalsError = $state(false);
	let signalsLoading = $state(true);

	async function loadSignals() {
		signalsLoading = true;
		signalsError = false;
		try {
			const res = await fetch(`${API}/signals`);
			if (!res.ok) throw new Error(res.statusText);
			signals = await res.json();
		} catch {
			signalsError = true;
		} finally {
			signalsLoading = false;
		}
	}

	// ── selected signal + date range ──────────────────────────────────────────
	let selectedSignal = $state(null);
	let filterText = $state('');

	const filteredSignals = $derived(
		filterText.trim()
			? signals.filter((s) => s.toLowerCase().includes(filterText.toLowerCase()))
			: signals
	);

	function defaultDateRange() {
		const end = new Date();
		const start = new Date(end - 7 * 24 * 3600 * 1000);
		return {
			start: start.toISOString().slice(0, 10),
			end: end.toISOString().slice(0, 10),
		};
	}

	let range = $state(defaultDateRange());

	// ── series fetch ──────────────────────────────────────────────────────────
	let seriesLoading = $state(false);
	let seriesError = $state(null);
	let seriesData = $state(null); // { signal, t, values }
	let metadata = $state(null);  // { start, end, count, gaps }

	async function fetchSeries(signal) {
		seriesLoading = true;
		seriesError = null;
		seriesData = null;
		metadata = null;
		try {
			const params = new URLSearchParams({
				signal,
				start: range.start,
				end:   range.end,
			});
			const res = await fetch(`${API}/series?${params}`);
			if (!res.ok) {
				const detail = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(detail.detail ?? res.statusText);
			}
			const data = await res.json();
			seriesData = data;
			metadata = computeMeta(data);
		} catch (e) {
			seriesError = e.message;
		} finally {
			seriesLoading = false;
		}
	}

	function computeMeta(data) {
		const values = data.values;
		const valid = values.filter((v) => v !== null);
		if (valid.length === 0) return { start: data.t[0], end: data.t.at(-1), count: 0, gaps: 0, min: null, max: null, mean: null };
		const nonNullIndices = values.map((v, i) => v !== null ? i : -1).filter((i) => i >= 0);
		// count consecutive null runs (gaps) between valid samples
		let gaps = 0;
		let inGap = false;
		for (const v of values) {
			if (v === null) { if (!inGap) { gaps++; inGap = true; } }
			else { inGap = false; }
		}
		const sum = valid.reduce((a, b) => a + b, 0);
		return {
			start: data.t[0],
			end: data.t.at(-1),
			count: valid.length,
			total: values.length,
			gaps,
			min: Math.min(...valid),
			max: Math.max(...valid),
			mean: sum / valid.length,
		};
	}

	// ── uPlot chart ───────────────────────────────────────────────────────────
	let chartContainer = $state(null);
	let uplot = null;

	function destroyChart() {
		if (uplot) { uplot.destroy(); uplot = null; }
	}

	function buildChart(data) {
		destroyChart();
		if (!chartContainer || !data) return;

		const ts = data.t.map((s) => Date.parse(s) / 1000); // seconds
		const vs = data.values.map((v) => (v === null ? NaN : v));

		const opts = {
			width:  chartContainer.clientWidth || 800,
			height: 260,
			cursor: { show: true },
			scales: { x: { time: true } },
			series: [
				{},
				{
					label: data.signal,
					stroke: '#38bdf8',
					width: 1.5,
					spanGaps: false,
				},
			],
			axes: [
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#1e293b' } },
				{ stroke: '#94a3b8', ticks: { stroke: '#334155' }, grid: { stroke: '#334155' } },
			],
		};
		uplot = new uPlot(opts, [ts, vs], chartContainer);
	}

	$effect(() => {
		if (seriesData) buildChart(seriesData);
	});

	// resize chart when container width changes
	let resizeObserver;
	$effect(() => {
		if (!chartContainer) return;
		resizeObserver = new ResizeObserver(() => {
			if (uplot && chartContainer) uplot.setSize({ width: chartContainer.clientWidth, height: 260 });
		});
		resizeObserver.observe(chartContainer);
		return () => resizeObserver?.disconnect();
	});

	onMount(loadSignals);
	onDestroy(destroyChart);

	// ── select a signal ───────────────────────────────────────────────────────
	function selectSignal(sig) {
		selectedSignal = sig;
		fetchSeries(sig);
	}

	function fmt(v, decimals = 2) {
		if (v === null || v === undefined) return '—';
		return v.toFixed(decimals);
	}

	function fmtDate(iso) {
		if (!iso) return '—';
		return new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
	}
</script>

<div class="explorer">
	<!-- ── left column: signal list ── -->
	<aside class="signal-list">
		<div class="list-header">
			<span class="list-title">Signals</span>
			<button class="icon-btn" onclick={loadSignals} title="Refresh">↻</button>
		</div>
		<input
			class="filter-input"
			type="text"
			placeholder="Filter…"
			bind:value={filterText}
		/>
		{#if signalsLoading}
			<div class="status">Loading…</div>
		{:else if signalsError}
			<div class="status error">⚠ API unreachable</div>
		{:else if signals.length === 0}
			<div class="status">No signals found</div>
		{:else}
			<ul class="sig-ul">
				{#each filteredSignals as sig}
					<li>
						<button
							class="sig-item"
							class:active={sig === selectedSignal}
							onclick={() => selectSignal(sig)}
						>{sig}</button>
					</li>
				{/each}
			</ul>
			{#if filterText && filteredSignals.length === 0}
				<div class="status">No match</div>
			{/if}
		{/if}
	</aside>

	<!-- ── right column: preview ── -->
	<div class="preview">
		{#if !selectedSignal}
			<div class="empty">Select a signal to preview</div>
		{:else}
			<div class="preview-header">
				<span class="sig-name">{selectedSignal}</span>
				<div class="range-controls">
					<label>From <input type="date" bind:value={range.start} /></label>
					<label>To   <input type="date" bind:value={range.end}   /></label>
					<button onclick={() => fetchSeries(selectedSignal)}>Load</button>
				</div>
			</div>

			{#if seriesLoading}
				<div class="status">Loading series…</div>
			{:else if seriesError}
				<div class="status error">⚠ {seriesError}</div>
			{:else if seriesData}
				<!-- metadata row -->
				{#if metadata}
					<div class="meta-row">
						<span>{fmtDate(metadata.start)} → {fmtDate(metadata.end)}</span>
						<span>{metadata.count} / {metadata.total} samples</span>
						{#if metadata.gaps > 0}<span class="gap-warn">{metadata.gaps} gap{metadata.gaps > 1 ? 's' : ''}</span>{/if}
						<span>min {fmt(metadata.min)} · max {fmt(metadata.max)} · mean {fmt(metadata.mean)}</span>
					</div>
				{/if}

				<!-- chart -->
				<div class="chart-wrap" bind:this={chartContainer}></div>
			{/if}
		{/if}
	</div>
</div>

<style>
	.explorer {
		display: flex;
		flex: 1;
		min-height: 0;
		overflow: hidden;
	}

	/* ── signal list ── */
	.signal-list {
		width: 380px;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		border-right: 1px solid #334155;
		background: #1e293b;
		overflow: hidden;
	}

	.list-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 10px 12px 6px;
		border-bottom: 1px solid #334155;
		flex-shrink: 0;
	}

	.list-title {
		font-size: 12px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #94a3b8;
	}

	.icon-btn {
		background: none;
		border: none;
		color: #64748b;
		cursor: pointer;
		font-size: 16px;
		padding: 0 4px;
		line-height: 1;
	}
	.icon-btn:hover { color: #94a3b8; }

	.filter-input {
		margin: 8px 10px;
		padding: 4px 8px;
		background: #0f172a;
		border: 1px solid #334155;
		border-radius: 4px;
		color: #f1f5f9;
		font-size: 12px;
		flex-shrink: 0;
	}
	.filter-input::placeholder { color: #475569; }

	.sig-ul {
		list-style: none;
		margin: 0;
		padding: 0;
		overflow-y: auto;
		flex: 1;
	}

	.sig-item {
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		color: #94a3b8;
		font-size: 12px;
		font-family: monospace;
		padding: 5px 12px;
		cursor: pointer;
		white-space: nowrap;
		display: block;
	}
	.sig-item:hover  { background: #0f172a; color: #f1f5f9; }
	.sig-item.active { background: #0f172a; color: #38bdf8; font-weight: 600; }

	.status { padding: 12px; font-size: 12px; color: #64748b; }
	.status.error { color: #f87171; }

	/* ── preview pane ── */
	.preview {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		padding: 16px 20px;
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

	.preview-header {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: 12px;
	}

	.sig-name {
		font-family: monospace;
		font-size: 14px;
		color: #38bdf8;
		font-weight: 600;
	}

	.range-controls {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: #94a3b8;
		flex-wrap: wrap;
	}

	.range-controls label {
		display: flex;
		align-items: center;
		gap: 4px;
	}

	.range-controls input[type='date'] {
		background: #0f172a;
		border: 1px solid #334155;
		border-radius: 4px;
		color: #f1f5f9;
		font-size: 12px;
		padding: 3px 6px;
		color-scheme: dark;
	}

	.range-controls button {
		background: #334155;
		color: #f1f5f9;
		border: 1px solid #475569;
		border-radius: 4px;
		padding: 3px 10px;
		font-size: 12px;
		cursor: pointer;
	}
	.range-controls button:hover { background: #475569; }

	.meta-row {
		display: flex;
		gap: 16px;
		flex-wrap: wrap;
		font-size: 12px;
		color: #94a3b8;
		padding: 6px 10px;
		background: #1e293b;
		border-radius: 4px;
	}

	.gap-warn { color: #fbbf24; }

	.chart-wrap {
		flex-shrink: 0;
	}

	/* uPlot overrides to match dark theme */
	:global(.uplot) { color: #94a3b8; }
	:global(.uplot .u-title) { color: #f1f5f9; }
	:global(.uplot canvas) { background: #0f172a; }
</style>
