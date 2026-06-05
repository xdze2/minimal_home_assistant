<script>
	import { MODELS } from '$lib/models.js';
	import GraphView from '$lib/GraphView.svelte';
	import PropertiesPanel from '$lib/PropertiesPanel.svelte';

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
	let selected = $state(null); // { kind: 'mass'|'boundary'|'source'|'resistance', id: string }

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

	// ── keyboard delete ───────────────────────────────────────────────────────
	function onKeyDown(e) {
		if ((e.key === 'Delete' || e.key === 'Backspace') && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'SELECT') {
			if (selected) ondelete(selected.kind, selected.id);
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
		<GraphView {model} {selected} onselect={(s) => (selected = s)} />
		<PropertiesPanel {model} {selected} {onpatch} {onadd} {ondelete} />
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
		flex-direction: column;
		height: 100vh;
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
</style>
