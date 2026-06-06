<script>
	import { onMount } from 'svelte';
	import uPlot from 'uplot';
	import 'uplot/dist/uPlot.min.css';

	const API = 'http://localhost:8001';

	let {
		model,
		inputs = {},       // node_id → signal name (from Inputs tab)
		range  = { start: '', end: '' },
	} = $props();

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

	// ── observations (mass node → signal) ────────────────────────────────────
	let observations = $state({});  // mass_node_id → signal name

	const massNodes = $derived(
		(model?.nodes ?? []).filter((n) => n.kind === 'mass')
	);

	function setObs(nodeId, value) {
		observations = { ...observations, [nodeId]: value };
	}

	// ── params table ──────────────────────────────────────────────────────────
	// Each row: { key: 'node_id.field', nominal: number, sigma_log: number }
	let paramRows = $state([]);

	// Re-populate when model changes (keep existing rows, add missing ones)
	$effect(() => {
		if (!model) return;
		const nodes = model.nodes ?? [];
		const existing = new Set(paramRows.map((r) => r.key));
		const next = [...paramRows];

		for (const n of nodes) {
			if (n.kind === 'resistance' && !existing.has(`${n.id}.R`)) {
				next.push({ key: `${n.id}.R`, nominal: n.R ?? 0.01, sigma_log: 0.5 });
			} else if (n.kind === 'mass' && !existing.has(`${n.id}.C`)) {
				next.push({ key: `${n.id}.C`, nominal: n.C ?? 1_000_000, sigma_log: 0.5 });
			} else if (n.kind === 'source' && !existing.has(`${n.id}.gain`)) {
				next.push({ key: `${n.id}.gain`, nominal: n.gain ?? 1.0, sigma_log: 0.5 });
			}
		}
		// only update if something was actually added
		if (next.length !== paramRows.length) paramRows = next;
	});

	function toggleParam(key) {
		const idx = paramRows.findIndex((r) => r.key === key);
		if (idx === -1) return;
		paramRows = paramRows.map((r, i) =>
			i === idx ? { ...r, fixed: !r.fixed } : r
		);
	}

	function updateParam(key, field, raw) {
		const value = field === 'key' ? raw : parseFloat(raw);
		if (field !== 'key' && isNaN(value)) return;
		paramRows = paramRows.map((r) => r.key === key ? { ...r, [field]: value } : r);
	}

	// ── fit config ────────────────────────────────────────────────────────────
	let obsSigma = $state(0.5);
	let method   = $state('nls');

	// ── fit run ───────────────────────────────────────────────────────────────
	let fitLoading = $state(false);
	let fitError   = $state(null);
	let fitResult  = $state(null);

	const canRun = $derived(
		!fitLoading &&
		range.start && range.end &&
		massNodes.some((n) => observations[n.id]?.trim()) &&
		paramRows.some((r) => !r.fixed)
	);

	async function runFit() {
		fitLoading = true;
		fitError   = null;
		fitResult  = null;

		const freeParams = {};
		for (const r of paramRows) {
			if (!r.fixed) freeParams[r.key] = { nominal: r.nominal, sigma_log: r.sigma_log };
		}

		const body = {
			model,
			start:        range.start,
			end:          range.end,
			inputs,
			observations: Object.fromEntries(
				Object.entries(observations).filter(([, v]) => v?.trim())
			),
			params:       freeParams,
			obs_sigma:    obsSigma,
			method,
			dt_minutes:   15,
		};

		try {
			const res = await fetch(`${API}/fit/run`, {
				method:  'POST',
				headers: { 'Content-Type': 'application/json' },
				body:    JSON.stringify(body),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({ detail: res.statusText }));
				throw new Error(typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail));
			}
			fitResult = await res.json();
		} catch (e) {
			fitError = e.message;
		} finally {
			fitLoading = false;
		}
	}

	// ── results table helpers ─────────────────────────────────────────────────
	function fmtParam(v) {
		if (v === null || v === undefined || isNaN(v)) return '—';
		if (Math.abs(v) < 0.001 || Math.abs(v) >= 1e6) return v.toExponential(3);
		return v.toPrecision(4);
	}

	function pctChange(fitted, nominal) {
		if (!nominal) return '—';
		const pct = ((fitted - nominal) / nominal) * 100;
		return (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
	}

	onMount(loadSignals);
</script>

<div class="fit-panel">
	<!-- action bar -->
	<div class="action-bar">
		<div class="method-group">
			<label class="radio-label">
				<input type="radio" bind:group={method} value="nls" />
				<span>NLS</span>
			</label>
			<label class="radio-label">
				<input type="radio" bind:group={method} value="mcmc" />
				<span>MCMC</span>
			</label>
		</div>

		<label class="obs-sigma-label">
			<span>obs σ (°C)</span>
			<input type="number" bind:value={obsSigma} min="0.01" step="0.1" style="width:70px" />
		</label>

		<button class="run-btn" onclick={runFit} disabled={!canRun}>
			{fitLoading ? 'Fitting…' : 'Run fit'}
		</button>
	</div>

	<div class="body">
		<!-- observations section -->
		<section class="section">
			<div class="section-header">
				Observations (measured temperatures)
				{#if signalsError}<span class="sig-warn" title="Cannot reach API">⚠</span>{/if}
			</div>

			<datalist id="signal-list-fit">
				{#each signals as s}<option value={s}></option>{/each}
			</datalist>

			{#if massNodes.length === 0}
				<p class="hint">No mass nodes in this model.</p>
			{:else}
				<div class="node-rows">
					{#each massNodes as node}
						<div class="node-row">
							<div class="node-label">
								<span class="kind-dot"></span>
								<span class="node-name">{node.label ?? node.id}</span>
								<span class="node-id">{node.id}</span>
							</div>
							<input
								type="text"
								list="signal-list-fit"
								placeholder="measurement/field?tag=val"
								value={observations[node.id] ?? ''}
								oninput={(e) => setObs(node.id, e.target.value)}
							/>
						</div>
					{/each}
				</div>
			{/if}
		</section>

		<!-- params section -->
		<section class="section">
			<div class="section-header">Free parameters</div>

			{#if paramRows.length === 0}
				<p class="hint">No parameters found. Load a study first.</p>
			{:else}
				<table class="params-table">
					<thead>
						<tr>
							<th></th>
							<th>Parameter</th>
							<th>Nominal</th>
							<th>σ log</th>
						</tr>
					</thead>
					<tbody>
						{#each paramRows as row (row.key)}
							<tr class:fixed={row.fixed}>
								<td>
									<input
										type="checkbox"
										checked={!row.fixed}
										onchange={() => toggleParam(row.key)}
									/>
								</td>
								<td class="param-key">{row.key}</td>
								<td>
									<input
										type="number"
										value={row.nominal}
										step="any"
										disabled={row.fixed}
										onchange={(e) => updateParam(row.key, 'nominal', e.target.value)}
									/>
								</td>
								<td>
									<input
										type="number"
										value={row.sigma_log}
										min="0.05" max="5" step="0.05"
										disabled={row.fixed}
										onchange={(e) => updateParam(row.key, 'sigma_log', e.target.value)}
									/>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/if}
		</section>

		<!-- results section -->
		{#if fitError}
			<div class="error-box">⚠ {fitError}</div>
		{/if}

		{#if fitResult}
			<section class="section">
				<div class="section-header">
					Results
					<span class="result-meta">
						{fitResult.method}
						{#if fitResult.elapsed_s !== undefined}· {fitResult.elapsed_s.toFixed(1)} s{/if}
						{#if fitResult.n_evals !== undefined}· {fitResult.n_evals} evals{/if}
						{#if fitResult.success !== undefined}
							<span class:ok={fitResult.success} class:fail={!fitResult.success}>
								· {fitResult.success ? '✓' : '✗ ' + fitResult.message}
							</span>
						{/if}
					</span>
				</div>

				<table class="results-table">
					<thead>
						<tr>
							<th>Parameter</th>
							<th>Nominal</th>
							<th>Fitted / Mean</th>
							<th>± σ</th>
							<th>Change</th>
						</tr>
					</thead>
					<tbody>
						{#each Object.keys(fitResult.params_nominal ?? fitResult.params_mean ?? {}) as key}
							{@const nominal = fitResult.params_nominal?.[key]}
							{@const fitted  = (fitResult.params_fitted ?? fitResult.params_mean)?.[key]}
							{@const std     = fitResult.params_std?.[key]}
							<tr>
								<td class="param-key">{key}</td>
								<td class="num">{fmtParam(nominal)}</td>
								<td class="num fitted">{fmtParam(fitted)}</td>
								<td class="num std">± {fmtParam(std)}</td>
								<td class="num change">{pctChange(fitted, nominal)}</td>
							</tr>
						{/each}
					</tbody>
				</table>

				{#if fitResult.cost !== undefined}
					<div class="cost-row">cost (½ RSS): {fitResult.cost.toFixed(4)}</div>
				{/if}
				{#if fitResult.acceptance_rate !== undefined}
					<div class="cost-row">acceptance rate: {(fitResult.acceptance_rate * 100).toFixed(1)}%</div>
				{/if}
			</section>
		{/if}
	</div>
</div>

<style>
	.fit-panel {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
		color: #f1f5f9;
	}

	.action-bar {
		display: flex;
		align-items: center;
		gap: 16px;
		padding: 10px 20px;
		background: #1e293b;
		border-bottom: 1px solid #334155;
		flex-shrink: 0;
	}

	.method-group { display: flex; gap: 14px; }

	.radio-label {
		display: flex; align-items: center; gap: 5px; cursor: pointer;
	}
	.radio-label span { font-size: 12px; color: #e2e8f0; }

	.obs-sigma-label {
		display: flex; align-items: center; gap: 6px;
		font-size: 11px; text-transform: uppercase;
		letter-spacing: 0.06em; color: #94a3b8;
	}

	.run-btn {
		background: #4f46e5; color: #f1f5f9;
		border: none; border-radius: 4px;
		padding: 8px 16px; font-size: 13px; font-weight: 600;
		cursor: pointer; transition: background 0.15s;
		margin-left: auto;
	}
	.run-btn:hover:not(:disabled) { background: #4338ca; }
	.run-btn:disabled { opacity: 0.5; cursor: not-allowed; }

	.body {
		flex: 1;
		overflow-y: auto;
		padding: 16px 20px;
		display: flex;
		flex-direction: column;
		gap: 20px;
		min-height: 0;
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.section-header {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #94a3b8;
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.sig-warn { color: #f59e0b; font-size: 11px; }
	.hint { font-size: 12px; color: #94a3b8; margin: 0; }

	/* observation rows */
	.node-rows { display: flex; flex-direction: column; gap: 6px; }

	.node-row {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		padding: 8px 12px;
		display: flex;
		flex-direction: column;
		gap: 5px;
	}

	.node-label { display: flex; align-items: center; gap: 5px; }

	.kind-dot {
		width: 7px; height: 7px;
		border-radius: 50%; flex-shrink: 0;
		background: #818cf8;
	}

	.node-name {
		font-size: 12px; color: #e2e8f0; font-weight: 500;
		flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
	}
	.node-id { font-size: 10px; font-family: monospace; color: #94a3b8; flex-shrink: 0; }

	input[type='text'],
	input[type='number'] {
		background: #0f172a;
		color: #e2e8f0;
		border: 1px solid #334155;
		border-radius: 4px;
		padding: 4px 8px;
		font-size: 12px;
		font-family: monospace;
		box-sizing: border-box;
	}
	input:focus { outline: none; border-color: #6366f1; }
	input:disabled { opacity: 0.4; }

	/* params table */
	.params-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 12px;
	}
	.params-table th {
		text-align: left;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #94a3b8;
		padding: 4px 8px 6px;
		border-bottom: 1px solid #334155;
	}
	.params-table td { padding: 4px 8px; }
	.params-table tr.fixed { opacity: 0.45; }
	.params-table tr:hover:not(.fixed) { background: #1e293b33; }

	.params-table input[type='number'] { width: 110px; }
	.params-table input[type='checkbox'] { cursor: pointer; accent-color: #6366f1; }

	.param-key {
		font-family: monospace;
		font-size: 11px;
		color: #e2e8f0;
	}

	/* results table */
	.results-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 12px;
	}
	.results-table th {
		text-align: left;
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #94a3b8;
		padding: 4px 8px 6px;
		border-bottom: 1px solid #334155;
	}
	.results-table td { padding: 5px 8px; }
	.results-table tr:nth-child(even) { background: #1e293b44; }

	.num { font-family: monospace; color: #cbd5e1; }
	.fitted { color: #38bdf8; font-weight: 600; }
	.std { color: #94a3b8; }
	.change { color: #a78bfa; }

	.result-meta {
		font-size: 11px;
		font-weight: 400;
		text-transform: none;
		letter-spacing: 0;
		color: #64748b;
	}
	.result-meta .ok   { color: #4ade80; }
	.result-meta .fail { color: #f87171; }

	.cost-row {
		font-size: 11px;
		font-family: monospace;
		color: #64748b;
		padding: 2px 8px;
	}

	.error-box {
		background: #1c0a0a;
		border: 1px solid #7f1d1d;
		border-radius: 4px;
		color: #f87171;
		padding: 12px 16px;
		font-size: 13px;
	}
</style>
