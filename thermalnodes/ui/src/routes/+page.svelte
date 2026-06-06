<script>
	import { onMount } from 'svelte';
	import GraphView from '$lib/GraphView.svelte';
	import PropertiesPanel from '$lib/PropertiesPanel.svelte';
	import DataExplorer from '$lib/DataExplorer.svelte';
	import SimulationRun from '$lib/SimulationRun.svelte';

	const API = 'http://localhost:8001';

	// ── page navigation ───────────────────────────────────────────────────────
	let activePage = $state('model');

	const PAGES = [
		{ id: 'data',       label: 'Data exploration' },
		{ id: 'model',      label: 'Model building'   },
		{ id: 'simulation', label: 'Simulation run'   },
	];

	// ── studies list ──────────────────────────────────────────────────────────
	let studies = $state([]);       // [{ id, label, room, source }]
	let studiesError = $state(null);

	async function loadStudies() {
		try {
			const res = await fetch(`${API}/studies`);
			if (!res.ok) throw new Error(res.statusText);
			studies = await res.json();
			studiesError = null;
		} catch (e) {
			studiesError = e.message;
		}
	}

	// ── current study state ───────────────────────────────────────────────────
	let selectedStudyId = $state(null);
	let model = $state(null);

	// sim state — lifted here so save/duplicate can snapshot them
	let simInputs  = $state({});
	let simRange   = $state({ start: '', end: '' });
	let simSolver  = $state('zoh');

	async function loadStudy(id) {
		try {
			const res = await fetch(`${API}/studies/${id}`);
			if (!res.ok) throw new Error(res.statusText);
			const study = await res.json();
			selectedStudyId = id;
			model = structuredClone(study.model ?? study);   // study or raw model JSON
			simInputs  = structuredClone(study.inputs  ?? {});
			simRange   = {
				start: study.start ?? '',
				end:   study.end   ?? '',
			};
			simSolver  = study.solver ?? 'zoh';
			selected = null;
		} catch (e) {
			alert(`Failed to load study: ${e.message}`);
		}
	}

	async function onStudyChange(e) {
		await loadStudy(e.target.value);
	}

	const selectedStudyMeta = $derived(studies.find((s) => s.id === selectedStudyId));

	// ── save study ────────────────────────────────────────────────────────────
	let saveId = $state('');
	let saveDialogOpen = $state(false);
	let saveLoading = $state(false);
	let saveError = $state(null);

	function openSaveDialog() {
		const meta = selectedStudyMeta;
		saveId = meta?.source === 'user' ? (selectedStudyId ?? '') : '';
		saveError = null;
		saveDialogOpen = true;
	}

	async function confirmSave() {
		if (!saveId.trim()) return;
		saveLoading = true;
		saveError = null;
		const study = {
			id:     saveId.trim(),
			label:  model?.name ?? saveId.trim(),
			room:   selectedStudyMeta?.room ?? null,
			model:  model,
			start:  simRange.start,
			end:    simRange.end,
			inputs: simInputs,
			solver: simSolver,
		};
		try {
			const res = await fetch(`${API}/studies/${saveId.trim()}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(study),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			saveDialogOpen = false;
			await loadStudies();
			selectedStudyId = saveId.trim();
		} catch (e) {
			saveError = e.message;
		} finally {
			saveLoading = false;
		}
	}

	// ── duplicate study ───────────────────────────────────────────────────────
	let dupId = $state('');
	let dupDialogOpen = $state(false);
	let dupLoading = $state(false);
	let dupError = $state(null);

	function openDupDialog() {
		dupId = selectedStudyId ? `${selectedStudyId}_copy` : '';
		dupError = null;
		dupDialogOpen = true;
	}

	async function confirmDuplicate() {
		if (!dupId.trim()) return;
		dupLoading = true;
		dupError = null;
		try {
			const res = await fetch(`${API}/studies/${selectedStudyId}/duplicate`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ new_id: dupId.trim() }),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			dupDialogOpen = false;
			await loadStudies();
			await loadStudy(dupId.trim());
		} catch (e) {
			dupError = e.message;
		} finally {
			dupLoading = false;
		}
	}

	// ── selection ─────────────────────────────────────────────────────────────
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

	// ── save / load JSON (model building tab) ────────────────────────────────
	function saveJSON() {
		const blob = new Blob([JSON.stringify(model, null, 2)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `${model.id ?? 'model'}.json`;
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

	onMount(async () => {
		await loadStudies();
		if (studies.length > 0) {
			await loadStudy(studies[0].id);
		}
	});
</script>

<svelte:window onkeydown={onKeyDown} />

<!-- ── save study dialog ─────────────────────────────────────────────────── -->
{#if saveDialogOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div class="dialog-backdrop" onclick={() => (saveDialogOpen = false)}>
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div class="dialog" onclick={(e) => e.stopPropagation()}>
			<div class="dialog-title">Save study</div>
			<label class="dialog-label">
				ID
				<input type="text" bind:value={saveId} placeholder="e.g. chambre_jan_2024_2r1c" />
			</label>
			{#if saveError}<div class="dialog-error">{saveError}</div>{/if}
			<div class="dialog-actions">
				<button onclick={() => (saveDialogOpen = false)}>Cancel</button>
				<button class="primary" onclick={confirmSave} disabled={saveLoading || !saveId.trim()}>
					{saveLoading ? 'Saving…' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- ── duplicate dialog ──────────────────────────────────────────────────── -->
{#if dupDialogOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div class="dialog-backdrop" onclick={() => (dupDialogOpen = false)}>
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div class="dialog" onclick={(e) => e.stopPropagation()}>
			<div class="dialog-title">Duplicate study</div>
			<label class="dialog-label">
				New ID
				<input type="text" bind:value={dupId} placeholder="e.g. chambre_feb_2024" />
			</label>
			{#if dupError}<div class="dialog-error">{dupError}</div>{/if}
			<div class="dialog-actions">
				<button onclick={() => (dupDialogOpen = false)}>Cancel</button>
				<button class="primary" onclick={confirmDuplicate} disabled={dupLoading || !dupId.trim()}>
					{dupLoading ? 'Duplicating…' : 'Duplicate'}
				</button>
			</div>
		</div>
	</div>
{/if}

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
		<!-- shared study picker header -->
		<header class="study-bar">
			{#if studiesError}
				<span class="api-warn">⚠ API unreachable</span>
			{:else}
				<select value={selectedStudyId ?? ''} onchange={onStudyChange} disabled={studies.length === 0}>
					{#if studies.length === 0}
						<option value="">Loading…</option>
					{/if}
					{#each studies as s}
						<option value={s.id}>
							{s.label}{s.room ? ` · ${s.room}` : ''}
						</option>
					{/each}
				</select>
				{#if selectedStudyMeta}
					<span class="source-badge" class:badge-example={selectedStudyMeta.source === 'example'} class:badge-user={selectedStudyMeta.source === 'user'}>
						{selectedStudyMeta.source}
					</span>
					{#if selectedStudyMeta.room}
						<span class="room-badge">{selectedStudyMeta.room}</span>
					{/if}
				{/if}
			{/if}
			<div class="spacer"></div>
			<button onclick={openSaveDialog} disabled={!model}>Save study</button>
			<button onclick={openDupDialog} disabled={!selectedStudyId}>Duplicate</button>
		</header>

		{#if activePage === 'model'}
			{#if model}
				<header>
					<span class="meta">{model.id} · schema {model.schema_version}</span>
					{#if model.notes}
						<span class="notes">{model.notes}</span>
					{/if}
					<div class="spacer"></div>
					<button onclick={() => fileInput?.click()}>Load JSON</button>
					<button onclick={saveJSON}>Export JSON</button>
					<input bind:this={fileInput} type="file" accept=".json" style="display:none" onchange={onFileChange} />
				</header>
				<div class="body">
					<GraphView {model} {selected} onselect={(s) => (selected = s)} {onaddedge} />
					<PropertiesPanel {model} {selected} {onpatch} {onadd} {ondelete} {ondeleteedge} />
				</div>
			{:else}
				<div class="placeholder">
					<h2>No study loaded</h2>
					<p>Select a study from the picker above, or check that the API is running.</p>
				</div>
			{/if}

		{:else if activePage === 'data'}
			<DataExplorer />

		{:else if activePage === 'simulation'}
			{#if model}
				<SimulationRun
					{model}
					bind:inputs={simInputs}
					bind:range={simRange}
					bind:solver={simSolver}
				/>
			{:else}
				<div class="placeholder">
					<h2>No study loaded</h2>
					<p>Select a study from the picker above.</p>
				</div>
			{/if}
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
	.nav-item:hover  { background: #334155; color: #f1f5f9; }
	.nav-item.active { background: #334155; color: #f1f5f9; font-weight: 600; }

	/* ── main area ── */
	.main {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	/* ── study bar ── */
	.study-bar {
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 8px 16px;
		background: #0f172a;
		border-bottom: 1px solid #1e293b;
		flex-shrink: 0;
	}

	.study-bar select {
		background: #1e293b;
		color: #f1f5f9;
		border: 1px solid #334155;
		border-radius: 4px;
		padding: 4px 8px;
		font-size: 13px;
		font-weight: 600;
		cursor: pointer;
		max-width: 360px;
	}

	.source-badge, .room-badge {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 6px;
		border-radius: 3px;
	}
	.badge-example { background: #1e3a5f; color: #93c5fd; }
	.badge-user    { background: #14532d; color: #86efac; }
	.room-badge    { background: #292524; color: #a8a29e; }

	.api-warn { font-size: 12px; color: #f59e0b; }

	/* ── model header ── */
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

	.meta   { font-size: 12px; opacity: 0.5; }
	.notes  {
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
	button:hover    { background: #475569; }
	button:disabled { opacity: 0.4; cursor: default; }
	button.primary  { background: #3b82f6; border-color: #2563eb; }
	button.primary:hover { background: #2563eb; }

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

	/* ── dialogs ── */
	.dialog-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0,0,0,0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 100;
	}

	.dialog {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		padding: 24px;
		width: 360px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.dialog-title {
		font-size: 15px;
		font-weight: 700;
		color: #f1f5f9;
	}

	.dialog-label {
		display: flex;
		flex-direction: column;
		gap: 5px;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #64748b;
	}

	.dialog-label input {
		background: #0f172a;
		color: #e2e8f0;
		border: 1px solid #334155;
		border-radius: 4px;
		padding: 6px 8px;
		font-size: 13px;
		font-family: monospace;
	}
	.dialog-label input:focus { outline: none; border-color: #6366f1; }

	.dialog-error {
		font-size: 12px;
		color: #f87171;
	}

	.dialog-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
	}
</style>
