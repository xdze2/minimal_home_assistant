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

	// ── patch: edit a node/edge field in-place ────────────────────────────────
	function onpatch(kind, id, patch) {
		if (kind === 'mass') {
			model = { ...model, masses: model.masses.map((n) => n.id === id ? { ...n, ...patch } : n) };
		} else if (kind === 'boundary') {
			model = { ...model, boundaries: model.boundaries.map((n) => n.id === id ? { ...n, ...patch } : n) };
		} else if (kind === 'source') {
			model = { ...model, sources: (model.sources ?? []).map((s) => s.id === id ? { ...s, ...patch } : s) };
		} else if (kind === 'resistance') {
			model = { ...model, resistances: (model.resistances ?? []).map((r) => r.id === id ? { ...r, ...patch } : r) };
		}
	}

	// ── add a new item ────────────────────────────────────────────────────────
	let idCounter = $state(0);

	function onadd(kind) {
		const uid = `${kind}_${++idCounter}`;
		if (kind === 'mass') {
			model = { ...model, masses: [...(model.masses ?? []), { id: uid, label: 'New mass', C: 1_000_000 }] };
		} else if (kind === 'boundary') {
			model = { ...model, boundaries: [...(model.boundaries ?? []), { id: uid, label: 'New boundary', T_source: 'signal_name' }] };
		} else if (kind === 'source') {
			const firstMass = model.masses?.[0]?.id ?? '';
			model = { ...model, sources: [...(model.sources ?? []), { id: uid, label: 'New source', node: firstMass, signal: 'signal_name', gain: 1.0 }] };
		} else if (kind === 'resistance') {
			const ids = [...(model.masses ?? []), ...(model.boundaries ?? [])];
			const from = ids[0]?.id ?? '';
			const to = ids[1]?.id ?? from;
			model = { ...model, resistances: [...(model.resistances ?? []), { id: uid, label: 'New resistance', from, to, R: 1.0 }] };
		}
		selected = { kind, id: uid };
	}

	// ── delete ────────────────────────────────────────────────────────────────
	function ondelete(kind, id) {
		if (kind === 'mass') {
			model = {
				...model,
				masses: model.masses.filter((n) => n.id !== id),
				resistances: (model.resistances ?? []).filter((r) => r.from !== id && r.to !== id),
				sources: (model.sources ?? []).filter((s) => s.node !== id)
			};
		} else if (kind === 'boundary') {
			model = {
				...model,
				boundaries: model.boundaries.filter((n) => n.id !== id),
				resistances: (model.resistances ?? []).filter((r) => r.from !== id && r.to !== id)
			};
		} else if (kind === 'source') {
			model = { ...model, sources: (model.sources ?? []).filter((s) => s.id !== id) };
		} else if (kind === 'resistance') {
			model = { ...model, resistances: (model.resistances ?? []).filter((r) => r.id !== id) };
		}
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
