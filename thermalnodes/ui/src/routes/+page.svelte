<script>
	import { onMount } from 'svelte';
	import GraphView from '$lib/GraphView.svelte';
	import PropertiesPanel from '$lib/PropertiesPanel.svelte';
	import InputsPanel from '$lib/InputsPanel.svelte';
	import SimulationRun from '$lib/SimulationRun.svelte';
	import FitPanel from '$lib/FitPanel.svelte';
	import HousePanel from '$lib/HousePanel.svelte';
	import MaterialsPanel from '$lib/MaterialsPanel.svelte';

	const API = 'http://localhost:8001';

	// ── navigation ────────────────────────────────────────────────────────────
	// activeSection: 'materials' | 'house' | 'studies'
	// activePage: sub-tab within studies: 'topology' | 'inputs' | 'run' | 'fit' | 'debug'
	let activeSection = $state('house');
	let activePage    = $state('topology');

	const STUDY_TABS = [
		{ id: 'topology', label: 'Topology' },
		{ id: 'inputs',   label: 'Inputs'   },
		{ id: 'run',      label: 'Run'      },
		{ id: 'fit',      label: 'Fit'      },
	];

	const DEV_TABS = [
		{ id: 'debug', label: 'JSON' },
	];

	// ── studies list ──────────────────────────────────────────────────────────
	let studies      = $state([]);
	let studiesError = $state(null);

	async function loadStudies() {
		try {
			const res = await fetch(`${API}/studies`);
			if (!res.ok) throw new Error(res.statusText);
			studies      = await res.json();
			studiesError = null;
		} catch (e) {
			studiesError = e.message;
		}
	}

	const exampleStudies = $derived(studies.filter((s) => s.source === 'example'));
	const userStudies    = $derived(studies.filter((s) => s.source === 'user'));

	// ── current study state ───────────────────────────────────────────────────
	let selectedStudyId  = $state(null);
	let model            = $state(null);
	let house            = $state({ schema_version: '0.1', rooms: [], elements: [] });
	let houseSavedSnapshot = $state(null);
	const houseDirty = $derived(houseSavedSnapshot !== null && JSON.stringify(house) !== houseSavedSnapshot);
	let houseSaveLoading = $state(false);
	let houseSaveError   = $state(null);

	async function loadHouse() {
		try {
			const res = await fetch(`${API}/house`);
			if (!res.ok) throw new Error(res.statusText);
			house = await res.json();
			houseSavedSnapshot = JSON.stringify(house);
		} catch (e) {
			// house.json may not exist yet — start blank, treat as unsaved
			houseSavedSnapshot = JSON.stringify(house);
		}
	}

	async function saveHouse() {
		houseSaveLoading = true;
		houseSaveError   = null;
		try {
			const res = await fetch(`${API}/house`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(house),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			houseSavedSnapshot = JSON.stringify(house);
		} catch (e) {
			houseSaveError = e.message;
		} finally {
			houseSaveLoading = false;
		}
	}

	let customMaterials  = $state({});  // user-defined materials
	let customConstants  = $state({});  // project-level constant overrides (h_i, h_e, …)
	let simInputs        = $state({});
	let simRange         = $state({ start: '', end: '' });
	let simSolver        = $state('zoh');
	let simObservations  = $state({});  // mass_node_id → signal name (key present = measured)

	const selectedStudyMeta = $derived(studies.find((s) => s.id === selectedStudyId));

	// ── stale / dirty tracking ────────────────────────────────────────────────
	let lastSavedSnapshot = $state(null);
	let lastRunSnapshot   = $state(null);

	function studySnapshot() {
		return JSON.stringify({ model, inputs: simInputs, observations: simObservations, start: simRange.start, end: simRange.end, solver: simSolver });
	}

	const studyDirty = $derived(lastSavedSnapshot !== null && studySnapshot() !== lastSavedSnapshot);
	const simStale   = $derived(lastRunSnapshot !== null && studySnapshot() !== lastRunSnapshot);

	function onRunSuccess() {
		lastRunSnapshot = studySnapshot();
	}

	async function loadStudy(id) {
		try {
			const res   = await fetch(`${API}/studies/${id}`);
			if (!res.ok) throw new Error(res.statusText);
			const study = await res.json();
			selectedStudyId  = id;
			model            = structuredClone(study.model ?? study);
			simInputs        = structuredClone(study.inputs ?? {});
			simRange         = { start: study.start ?? '', end: study.end ?? '' };
			simSolver        = study.solver ?? 'zoh';
			simObservations  = structuredClone(study.observations ?? {});
			selected         = null;
			lastSavedSnapshot = studySnapshot();
			lastRunSnapshot   = null;
		} catch (e) {
			alert(`Failed to load study: ${e.message}`);
		}
	}

	async function openStudy(id) {
		await loadStudy(id);
		activeSection = 'studies';
		activePage    = 'topology';
	}

	// ── save study ────────────────────────────────────────────────────────────
	let saveId         = $state('');
	let saveDialogOpen = $state(false);
	let saveLoading    = $state(false);
	let saveError      = $state(null);

	function openSaveDialog() {
		saveId    = selectedStudyMeta?.source === 'user' ? (selectedStudyId ?? '') : '';
		saveError = null;
		saveDialogOpen = true;
	}

	async function confirmSave() {
		if (!saveId.trim()) return;
		saveLoading = true;
		saveError   = null;
		const study = {
			id:           saveId.trim(),
			label:        model?.name ?? saveId.trim(),
			room:         selectedStudyMeta?.room ?? null,
			model,
			start:        simRange.start,
			end:          simRange.end,
			inputs:       simInputs,
			observations: simObservations,
			solver:       simSolver,
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
			saveDialogOpen    = false;
			selectedStudyId   = saveId.trim();
			lastSavedSnapshot = studySnapshot();
			await loadStudies();
		} catch (e) {
			saveError = e.message;
		} finally {
			saveLoading = false;
		}
	}

	// ── duplicate study ───────────────────────────────────────────────────────
	let dupSourceId    = $state(null);
	let dupId          = $state('');
	let dupDialogOpen  = $state(false);
	let dupLoading     = $state(false);
	let dupError       = $state(null);

	function openDupDialog(sourceId) {
		dupSourceId   = sourceId;
		dupId         = `${sourceId}_copy`;
		dupError      = null;
		dupDialogOpen = true;
	}

	async function confirmDuplicate() {
		if (!dupId.trim()) return;
		dupLoading = true;
		dupError   = null;
		try {
			const res = await fetch(`${API}/studies/${dupSourceId}/duplicate`, {
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
			await openStudy(dupId.trim());
		} catch (e) {
			dupError = e.message;
		} finally {
			dupLoading = false;
		}
	}

	// ── param groups (identifiability) ───────────────────────────────────────
	let paramGroups = $state([]);  // list[list[str]] from /fit/preview-groups

	async function refreshGroups(currentModel) {
		if (!currentModel) { paramGroups = []; return; }
		const nodes = currentModel.nodes ?? [];
		const keys = nodes.flatMap((n) => {
			if (n.kind === 'resistance') return [`${n.id}.R`];
			if (n.kind === 'mass')       return [`${n.id}.C`];
			if (n.kind === 'source')     return [`${n.id}.gain`];
			return [];
		});
		if (keys.length === 0) { paramGroups = []; return; }
		try {
			const res = await fetch(`${API}/fit/preview-groups`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ model: currentModel, param_keys: keys }),
			});
			if (res.ok) paramGroups = await res.json();
		} catch { /* silently ignore — groups are cosmetic */ }
	}

	$effect(() => { refreshGroups(model); });

	// ── graph node selection + operations ─────────────────────────────────────
	let selected  = $state(null);
	let idCounter = $state(0);

	function onpatch(kind, id, patch) {
		model = { ...model, nodes: model.nodes.map((n) => n.id === id && n.kind === kind ? { ...n, ...patch } : n) };
	}

	function onadd(kind) {
		const uid = `${kind}_${++idCounter}`;
		const newNode =
			kind === 'mass'       ? { id: uid, kind, label: 'New mass',       C: 1_000_000 } :
			kind === 'boundary'   ? { id: uid, kind, label: 'New boundary',   T_source: 'signal_name' } :
			kind === 'source'     ? { id: uid, kind, label: 'New source',     signal: 'signal_name', gain: 1.0 } :
			/* resistance */        { id: uid, kind, label: 'New resistance', R: 1.0 };
		model    = { ...model, nodes: [...(model.nodes ?? []), newNode] };
		selected = { kind, id: uid };
	}

	function ondelete(kind, id) {
		model    = { ...model, nodes: model.nodes.filter((n) => !(n.id === id && n.kind === kind)), edges: (model.edges ?? []).filter((e) => e.from !== id && e.to !== id) };
		selected = null;
	}

	function onaddedge(from, to) {
		const exists = (model.edges ?? []).some((e) => e.from === from && e.to === to);
		if (!exists && from !== to) model = { ...model, edges: [...(model.edges ?? []), { from, to }] };
	}

	function ondeleteedge(from, to) {
		model    = { ...model, edges: (model.edges ?? []).filter((e) => !(e.from === from && e.to === to)) };
		selected = null;
	}

	function onKeyDown(e) {
		if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'SELECT') return;
		if (e.key === 'Delete' || e.key === 'Backspace') {
			if (selected?.kind === 'edge') ondeleteedge(selected.from, selected.to);
			else if (selected) ondelete(selected.kind, selected.id);
		}
	}

	onMount(async () => {
		await Promise.all([loadStudies(), loadHouse()]);
	});
</script>

<svelte:window onkeydown={onKeyDown} />

<!-- ── save dialog ────────────────────────────────────────────────────────── -->
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

<!-- ── shell ─────────────────────────────────────────────────────────────── -->
<div class="shell">

	<!-- left nav -->
	<nav class="sidenav">
		<div class="nav-top">
			<div class="nav-logo">miniha</div>

			<!-- top-level sections -->
			<button class="nav-item" class:active={activeSection === 'materials'} onclick={() => (activeSection = 'materials')}>
				Materials
			</button>
			<button class="nav-item" class:active={activeSection === 'house'} onclick={() => (activeSection = 'house')}>
				House
			</button>
			<button class="nav-item" class:active={activeSection === 'studies'} onclick={() => (activeSection = 'studies')}>
				Studies
			</button>

			<!-- study sub-tabs, shown when a study is selected and in studies section -->
			{#if selectedStudyId && activeSection === 'studies'}
				<div class="nav-divider"></div>
				<button class="nav-item nav-back" onclick={() => { selectedStudyId = null; model = null; }}>← all studies</button>
				<div class="nav-study-id">{selectedStudyId}</div>
				{#each STUDY_TABS as t}
					<button
						class="nav-item nav-tab"
						class:active={activePage === t.id}
						onclick={() => (activePage = t.id)}
					>{t.label}</button>
				{/each}
				<div class="nav-divider"></div>
				{#each DEV_TABS as t}
					<button
						class="nav-item nav-tab nav-dev"
						class:active={activePage === t.id}
						onclick={() => (activePage = t.id)}
					>{t.label}</button>
				{/each}
			{/if}
		</div>

		{#if activeSection === 'house'}
			<div class="nav-bottom">
				{#if houseSaveError}<div class="nav-save-error">{houseSaveError}</div>{/if}
				<button class="nav-save" class:dirty={houseDirty} onclick={saveHouse} disabled={houseSaveLoading}>
					{houseSaveLoading ? 'Saving…' : `Save${houseDirty ? ' ●' : ''}`}
				</button>
			</div>
		{/if}

		{#if selectedStudyId && activeSection === 'studies'}
			<div class="nav-bottom">
				<button class="nav-save" class:dirty={studyDirty} onclick={openSaveDialog}>
					Save{studyDirty ? ' ●' : ''}
				</button>
			</div>
		{/if}
	</nav>

	<!-- main area -->
	<div class="main">

		{#if activeSection === 'materials'}
			<div class="body">
				<MaterialsPanel
					materials={customMaterials}
					{customConstants}
					onchange={(m) => (customMaterials = m)}
					onconstants={(c) => (customConstants = c)}
				/>
			</div>

		{:else if activeSection === 'house'}
			<div class="body">
				<HousePanel {house} onchange={(h) => (house = h)} {customMaterials} />
			</div>

		{:else if activeSection === 'studies'}
			{#if !selectedStudyId || activePage === 'browse'}
				<!-- ── study browser ── -->
				<div class="home">
					<div class="home-header">
						{#if studiesError}
							<span class="api-warn">⚠ API unreachable — {studiesError}</span>
						{:else}
							<span class="home-title">Studies</span>
						{/if}
					</div>

					<div class="home-groups">
						{#if exampleStudies.length > 0}
							<div class="study-group">
								<div class="group-label">examples/</div>
								<div class="study-grid">
									{#each exampleStudies as s}
										<div class="study-card" class:selected={s.id === selectedStudyId}>
											<button class="card-open" onclick={() => openStudy(s.id)}>
												<div class="card-id">{s.id}</div>
												{#if s.room}<div class="card-room">{s.room}</div>{/if}
												<div class="card-badge badge-example">example</div>
											</button>
											<div class="card-actions">
												<button class="card-action" onclick={() => openDupDialog(s.id)} title="Duplicate">⎘</button>
											</div>
										</div>
									{/each}
								</div>
							</div>
						{/if}

						<div class="study-group">
							<div class="group-label">user/</div>
							<div class="study-grid">
								{#each userStudies as s}
									<div class="study-card" class:selected={s.id === selectedStudyId}>
										<button class="card-open" onclick={() => openStudy(s.id)}>
											<div class="card-id">{s.id}</div>
											{#if s.room}<div class="card-room">{s.room}</div>{/if}
											<div class="card-badge badge-user">user</div>
										</button>
										<div class="card-actions">
											<button class="card-action" onclick={() => openDupDialog(s.id)} title="Duplicate">⎘</button>
										</div>
									</div>
								{/each}

								{#if userStudies.length === 0}
									<div class="study-card card-empty">
										<span>No user studies yet.<br/>Duplicate an example to start.</span>
									</div>
								{/if}
							</div>
						</div>
					</div>
				</div>

			{:else if activePage === 'topology'}
				{#if model}
					<div class="body">
						<PropertiesPanel {model} {selected} {onpatch} {onadd} {ondelete} {ondeleteedge} />
						<GraphView {model} {selected} onselect={(s) => (selected = s)} {onaddedge} groups={paramGroups} />
					</div>
				{/if}

			{:else if activePage === 'inputs'}
				{#if model}
					<div class="body scrollable">
						<InputsPanel {model} bind:inputs={simInputs} bind:range={simRange} bind:observations={simObservations} />
					</div>
				{/if}

			{:else if activePage === 'run'}
				{#if model}
					<SimulationRun {model} inputs={simInputs} range={simRange} observations={simObservations} bind:solver={simSolver} {simStale} {onRunSuccess} />
				{/if}

			{:else if activePage === 'fit'}
				{#if model}
					<FitPanel {model} inputs={simInputs} range={simRange} observations={simObservations} groups={paramGroups} />
				{/if}

			{:else if activePage === 'debug'}
				<div class="debug-view">
					<pre>{JSON.stringify({ model, inputs: simInputs, range: simRange, solver: simSolver }, null, 2)}</pre>
				</div>
			{/if}
		{/if}

	</div>
</div>

<style>
.shell {
		display: flex;
		height: 100vh;
		overflow: hidden;
	}

	/* ── side nav ── */
	.sidenav {
		width: 176px;
		flex-shrink: 0;
		background: #1e293b;
		border-right: 1px solid #334155;
		display: flex;
		flex-direction: column;
		padding: 0;
		overflow: hidden;
	}

	.nav-top {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 12px 0 8px;
		overflow-y: auto;
		overflow-x: hidden;
	}

	.nav-bottom {
		padding: 8px 10px 12px;
		border-top: 1px solid #334155;
		flex-shrink: 0;
	}

	.nav-logo {
		color: #94a3b8;
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		padding: 4px 16px 14px;
	}

	.nav-item {
		background: none;
		border: none;
		color: #94a3b8;
		font-size: 13px;
		text-align: left;
		padding: 7px 16px;
		cursor: pointer;
		transition: background 0.1s, color 0.1s;
		border-radius: 0;
	}
	.nav-item:hover  { background: #334155; color: #f1f5f9; }
	.nav-item.active { background: #334155; color: #f1f5f9; font-weight: 600; }

	.nav-tab  { padding-left: 24px; font-size: 12px; }
	.nav-back { font-size: 11px; color: #475569; }
	.nav-back:hover { color: #94a3b8; }
	.nav-dev  { color: #475569; font-style: italic; }
	.nav-dev:hover  { color: #94a3b8; }
	.nav-dev.active { color: #94a3b8; font-weight: 600; }

	.nav-divider {
		height: 1px;
		background: #334155;
		margin: 8px 12px;
	}

	.nav-study-id {
		font-size: 10px;
		font-family: monospace;
		color: #94a3b8;
		padding: 0 16px 4px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.nav-save {
		width: 100%;
		background: #1e3a5f;
		color: #93c5fd;
		border: 1px solid #1e4976;
		border-radius: 4px;
		padding: 6px 12px;
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
		text-align: center;
		transition: background 0.1s;
		box-sizing: border-box;
	}
	.nav-save:hover { background: #1e4976; }
	.nav-save.dirty { border-color: #f59e0b; color: #fcd34d; }

	.nav-save-error {
		font-size: 10px;
		color: #f87171;
		margin-bottom: 4px;
		word-break: break-word;
	}

	/* ── main area ── */
	.main {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		overflow: hidden;
	}

	/* ── home view ── */
	.home {
		flex: 1;
		display: flex;
		flex-direction: column;
		padding: 28px 32px;
		overflow-y: auto;
		gap: 24px;
	}

	.home-header {
		display: flex;
		align-items: center;
		gap: 16px;
	}

	.home-title {
		font-size: 20px;
		font-weight: 700;
		color: #f1f5f9;
	}

	.api-warn { font-size: 13px; color: #f59e0b; }

	.home-groups {
		display: flex;
		flex-direction: column;
		gap: 28px;
	}

	.study-group { display: flex; flex-direction: column; gap: 12px; }

	.group-label {
		font-size: 11px;
		font-family: monospace;
		font-weight: 700;
		color: #94a3b8;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.study-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
	}

	.study-card {
		width: 200px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		transition: border-color 0.15s;
	}
	.study-card:hover { border-color: #475569; }
	.study-card.selected { border-color: #3b82f6; }

	.card-open {
		background: none;
		border: none;
		padding: 14px 14px 10px;
		text-align: left;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: 5px;
		flex: 1;
	}
	.card-open:hover { background: #0f172a22; }

	.card-id {
		font-size: 12px;
		font-family: monospace;
		font-weight: 600;
		color: #e2e8f0;
		word-break: break-all;
	}

	.card-room {
		font-size: 11px;
		color: #94a3b8;
	}

	.card-badge {
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 6px;
		border-radius: 3px;
		align-self: flex-start;
		margin-top: 2px;
	}
	.badge-example { background: #1e3a5f; color: #93c5fd; }
	.badge-user    { background: #14532d; color: #86efac; }

	.card-actions {
		border-top: 1px solid #334155;
		padding: 5px 8px;
		display: flex;
		gap: 4px;
		justify-content: flex-end;
	}

	.card-action {
		background: none;
		border: none;
		color: #94a3b8;
		font-size: 15px;
		cursor: pointer;
		padding: 2px 6px;
		border-radius: 3px;
		line-height: 1;
	}
	.card-action:hover { background: #334155; color: #f1f5f9; }

	.card-empty {
		border-style: dashed;
		padding: 20px;
		color: #94a3b8;
		font-size: 12px;
		line-height: 1.6;
		align-items: center;
		justify-content: center;
		text-align: center;
		cursor: default;
		width: auto;
		flex: 1;
		max-width: 300px;
	}

	/* ── body / content areas ── */
	.body {
		flex: 1;
		display: flex;
		min-height: 0;
	}
	.body.scrollable { overflow-y: auto; }

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

	.debug-view {
		flex: 1;
		overflow: auto;
		padding: 20px 24px;
	}
	.debug-view pre {
		margin: 0;
		font-family: monospace;
		font-size: 12px;
		color: #64748b;
		line-height: 1.6;
		white-space: pre-wrap;
	}

	/* ── buttons (global defaults) ── */
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
		color: #94a3b8;
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

	.dialog-error { font-size: 12px; color: #f87171; }

	.dialog-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
	}
</style>
