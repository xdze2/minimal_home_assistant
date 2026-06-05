<script>
	import { MODELS } from '$lib/models.js';
	import GraphView from '$lib/GraphView.svelte';
	import PropertiesPanel from '$lib/PropertiesPanel.svelte';

	// ── page navigation ───────────────────────────────────────────────────────
	let activePage = $state('model');

	const PAGES = [
		{ id: 'data',       label: 'Data exploration' },
		{ id: 'model',      label: 'Model building'   },
		{ id: 'simulation', label: 'Simulation run'   },
	];

	// ── model state ───────────────────────────────────────────────────────────
	let selectedModelId = $state(MODELS[0].id);
	// Deep-clone so edits don't mutate the imported constant
	let model = $state(structuredClone(MODELS[0].model));

	function onModelChange(e) {
		selectedModelId = e.target.value;
		const found = MODELS.find((m) => m.id === selectedModelId);
		if (found) {
			model = structuredClone(found.model);
			selected = null;
		}
	}

	const selectedMeta = $derived(MODELS.find((m) => m.id === selectedModelId));

	// ── selection ─────────────────────────────────────────────────────────────
	// node: { kind: 'mass'|'boundary'|'source'|'resistance', id: string }
	// edge: { kind: 'edge', from: string, to: string }
	let selected = $state(null);

	// ── patch: edit a node field in-place ────────────────────────────────────
	function onpatch(kind, id, patch) {
		model = { ...model, nodes: model.nodes.map((n) => n.id === id && n.kind === kind ? { ...n, ...patch } : n) };
	}

	// ── add a new item ────────────────────────────────────────────────────────
	let idCounter = $state(0);

	function onadd(kind) {
		const uid = `${kind}_${++idCounter}`;
		let newNode;
		if (kind === 'mass') {
			newNode = { id: uid, kind: 'mass', label: 'New mass', C: 1_000_000 };
		} else if (kind === 'boundary') {
			newNode = { id: uid, kind: 'boundary', label: 'New boundary', T_source: 'signal_name' };
		} else if (kind === 'source') {
			newNode = { id: uid, kind: 'source', label: 'New source', signal: 'signal_name', gain: 1.0 };
		} else if (kind === 'resistance') {
			newNode = { id: uid, kind: 'resistance', label: 'New resistance', R: 1.0 };
		}
		model = { ...model, nodes: [...(model.nodes ?? []), newNode] };
		selected = { kind, id: uid };
	}

	// ── delete ────────────────────────────────────────────────────────────────
	function ondelete(kind, id) {
		model = {
			...model,
			nodes: model.nodes.filter((n) => !(n.id === id && n.kind === kind)),
			edges: (model.edges ?? []).filter((e) => e.from !== id && e.to !== id)
		};
		selected = null;
	}

	// ── edge operations ───────────────────────────────────────────────────────
	function onaddedge(from, to) {
		// prevent duplicate edges
		const exists = (model.edges ?? []).some((e) => e.from === from && e.to === to);
		if (!exists && from !== to) {
			model = { ...model, edges: [...(model.edges ?? []), { from, to }] };
		}
	}

	function ondeleteedge(from, to) {
		model = { ...model, edges: (model.edges ?? []).filter((e) => !(e.from === from && e.to === to)) };
		selected = null;
	}

	// ── keyboard shortcuts ────────────────────────────────────────────────────
	function onKeyDown(e) {
		if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'SELECT') return;
		if (e.key === 'Delete' || e.key === 'Backspace') {
			if (selected?.kind === 'edge') ondeleteedge(selected.from, selected.to);
			else if (selected) ondelete(selected.kind, selected.id);
		}
	}

	// ── save / load JSON ──────────────────────────────────────────────────────
	function saveJSON() {
		const blob = new Blob([JSON.stringify(model, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${model.id}.json`;
		a.click();
		URL.revokeObjectURL(url);
	}

	let fileInput = $state(null);

	function onFileChange(e) {
		const file = e.target.files?.[0];
		if (!file) return;
		const reader = new FileReader();
		reader.onload = (ev) => {
			try {
				model = JSON.parse(ev.target.result);
				selected = null;
			} catch {
				alert('Invalid JSON');
			}
		};
		reader.readAsText(file);
		e.target.value = '';
	}
</script>

<svelte:window onkeydown={onKeyDown} />

<div class="shell">
	<nav class="sidenav">
		<div class="nav-logo">miniha</div>
		{#each PAGES as p}
			<button
				class="nav-item"
				class:active={activePage === p.id}
				onclick={() => (activePage = p.id)}
			>{p.label}</button>
		{/each}
	</nav>

	<div class="main">
		{#if activePage === 'model'}
			<header>
				<select value={selectedModelId} onchange={onModelChange}>
					{#each MODELS as m}
						<option value={m.id}>{m.label}</option>
					{/each}
				</select>
				<span class="meta">{model.id} · schema {model.schema_version}</span>
				{#if model.notes}
					<span class="notes">{model.notes}</span>
				{/if}
				<div class="spacer"></div>
				<button onclick={() => fileInput?.click()}>Load JSON</button>
				<button onclick={saveJSON}>Save JSON</button>
				<input bind:this={fileInput} type="file" accept=".json" style="display:none" onchange={onFileChange} />
			</header>
			<div class="body">
				<GraphView {model} {selected} onselect={(s) => (selected = s)} {onaddedge} />
				<PropertiesPanel {model} {selected} {onpatch} {onadd} {ondelete} {ondeleteedge} />
			</div>

		{:else if activePage === 'data'}
			<div class="placeholder">
				<h2>Data exploration</h2>
				<p>Browse and inspect available signals and datasets.</p>
			</div>

		{:else if activePage === 'simulation'}
			<div class="placeholder">
				<h2>Simulation run</h2>
				<p>Configure and launch simulation runs.</p>
			</div>
		{/if}
	</div>
</div>

<style>
	:global(body) {
		margin: 0;
		font-family: sans-serif;
		background: #0f172a;
	}

	.shell {
		display: flex;
		flex-direction: row;
		height: 100vh;
	}

	/* ── side nav ── */
	.sidenav {
		display: flex;
		flex-direction: column;
		width: 160px;
		flex-shrink: 0;
		background: #1e293b;
		border-right: 1px solid #334155;
		padding: 12px 0;
		gap: 2px;
	}

	.nav-logo {
		color: #94a3b8;
		font-size: 13px;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		padding: 8px 16px 16px;
	}

	.nav-item {
		background: none;
		border: none;
		color: #94a3b8;
		font-size: 13px;
		text-align: left;
		padding: 8px 16px;
		cursor: pointer;
		border-radius: 0;
		transition: background 0.1s, color 0.1s;
	}
	.nav-item:hover { background: #334155; color: #f1f5f9; }
	.nav-item.active { background: #334155; color: #f1f5f9; font-weight: 600; }

	/* ── main area ── */
	.main {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	header {
		display: flex;
		align-items: baseline;
		gap: 16px;
		padding: 10px 20px;
		background: #1e293b;
		color: #f1f5f9;
		flex-shrink: 0;
		border-bottom: 1px solid #334155;
	}

	select {
		background: #334155;
		color: #f1f5f9;
		border: 1px solid #475569;
		border-radius: 4px;
		padding: 4px 8px;
		font-size: 14px;
		font-weight: 600;
		cursor: pointer;
	}

	.meta { font-size: 12px; opacity: 0.5; }

	.notes {
		font-size: 11px;
		opacity: 0.4;
		font-style: italic;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		max-width: 400px;
	}

	.spacer { flex: 1; }

	button {
		background: #334155;
		color: #f1f5f9;
		border: 1px solid #475569;
		border-radius: 4px;
		padding: 4px 12px;
		font-size: 13px;
		cursor: pointer;
	}
	button:hover { background: #475569; }

	.body {
		flex: 1;
		display: flex;
		min-height: 0;
	}

	.placeholder {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		color: #94a3b8;
		gap: 8px;
	}
	.placeholder h2 { margin: 0; font-size: 20px; color: #f1f5f9; }
	.placeholder p  { margin: 0; font-size: 14px; }
</style>
