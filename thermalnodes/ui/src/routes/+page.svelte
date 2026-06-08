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
	// activeSection: 'materials' | 'houses' | 'house'
	// simPaneTab: right-pane tab: 'studies' | 'sim' | 'rc' | 'topology' | 'inputs' | 'run' | 'fit' | 'debug'
	let activeSection = $state('houses');

	// ── houses list ───────────────────────────────────────────────────────────
	let housesList     = $state([]);
	let housesError    = $state(null);

	async function loadHousesList() {
		try {
			const res = await fetch(`${API}/houses`);
			if (!res.ok) throw new Error(res.statusText);
			housesList  = await res.json();
			housesError = null;
		} catch (e) {
			housesError = e.message;
		}
	}

	// ── current house ─────────────────────────────────────────────────────────
	let houseName          = $state(null);  // name of the currently open house
	let house              = $state(null);
	let houseSavedSnapshot = $state(null);
	const houseDirty = $derived(houseSavedSnapshot !== null && JSON.stringify(house) !== houseSavedSnapshot);
	let houseSaveLoading = $state(false);
	let houseSaveError   = $state(null);

	async function loadHouse(name) {
		try {
			const res = await fetch(`${API}/houses/${name}`);
			if (!res.ok) throw new Error(res.statusText);
			house              = await res.json();
			houseName          = name;
			houseSavedSnapshot = JSON.stringify(house);
		} catch (e) {
			alert(`Failed to load house: ${e.message}`);
		}
	}

	async function openHouse(name) {
		await loadHouse(name);
		activeSection = 'house';
	}

	async function saveHouse() {
		if (!houseName) return;
		houseSaveLoading = true;
		houseSaveError   = null;
		// Strip computed fields (_model_hash, _stale_*) before saving
		const toSave = stripComputed(house);
		try {
			const res = await fetch(`${API}/houses/${houseName}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(toSave),
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

	function stripComputed(obj) {
		if (Array.isArray(obj)) return obj.map(stripComputed);
		if (obj && typeof obj === 'object') {
			const out = {};
			for (const [k, v] of Object.entries(obj)) {
				if (!k.startsWith('_')) out[k] = stripComputed(v);
			}
			return out;
		}
		return obj;
	}

	async function deleteHouse() {
		if (!houseName) return;
		try {
			const res = await fetch(`${API}/houses/${houseName}`, { method: 'DELETE' });
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			houseName = null;
			house = null;
			selectedStudyId = null;
			model = null;
			activeSection = 'houses';
			await loadHousesList();
		} catch (e) {
			alert(`Failed to delete house: ${e.message}`);
		}
	}

	async function createNewHouse() {
		try {
			const res = await fetch(`${API}/houses`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					label: 'New house',
					schema_version: '0.3',
					rooms: [],
					elements: [],
					studies: [],
				}),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			const data = await res.json();
			await loadHousesList();
			await openHouse(data.name);
		} catch (e) {
			alert(`Failed to create house: ${e.message}`);
		}
	}

	let customMaterials  = $state({});
	let customConstants  = $state({});

	// ── studies (embedded in house) ───────────────────────────────────────────
	const studies = $derived(house?.studies ?? []);

	// ── current study state ───────────────────────────────────────────────────
	let selectedStudyId  = $state(null);
	let model            = $state(null);
	let simInputs        = $state({});
	let simRange         = $state({ start: '', end: '' });
	let simSolver        = $state('zoh');
	let simObservations  = $state({});

	const selectedStudy = $derived(studies.find((s) => s.id === selectedStudyId));

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

	function loadStudyIntoState(study) {
		const snap          = $state.snapshot(study);
		model            = snap.model ?? snap;
		simInputs        = snap.inputs ?? {};
		simRange         = { start: snap.start ?? '', end: snap.end ?? '' };
		simSolver        = snap.solver ?? 'zoh';
		simObservations  = snap.observations ?? {};
		selected         = null;
		lastSavedSnapshot = studySnapshot();
		lastRunSnapshot   = null;
	}

	async function openStudy(studyId) {
		const study = studies.find((s) => s.id === studyId);
		if (!study) return;
		selectedStudyId = studyId;
		loadStudyIntoState(study);
		activeSection = 'house';
		simPaneTab    = 'topology';
	}

	// ── save study ────────────────────────────────────────────────────────────
	let saveLoading = $state(false);
	let saveError   = $state(null);

	async function saveStudy() {
		if (!houseName || !selectedStudyId) return;
		saveLoading = true;
		saveError   = null;
		const studyPayload = {
			id:           selectedStudyId,
			label:        model?.name ?? selectedStudyId,
			model,
			start:        simRange.start,
			end:          simRange.end,
			inputs:       simInputs,
			observations: simObservations,
			solver:       simSolver,
		};
		// Preserve run/fit records from existing study
		if (selectedStudy?.run) studyPayload.run = selectedStudy.run;
		if (selectedStudy?.fit) studyPayload.fit = selectedStudy.fit;
		try {
			const res = await fetch(`${API}/houses/${houseName}/studies/${selectedStudyId}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(studyPayload),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			lastSavedSnapshot = studySnapshot();
			await loadHouse(houseName);
		} catch (e) {
			saveError = e.message;
		} finally {
			saveLoading = false;
		}
	}

	// ── simulation pane (house view) ─────────────────────────────────────────
	let simPaneTab  = $state('studies'); // 'studies' | 'sim' | 'rc' | 'topology' | 'inputs' | 'run' | 'fit' | 'debug'
	let rangeMode   = $state('duration'); // 'dates' | 'duration'
	let triggerRun  = $state(/** @type {(() => void) | null} */ (null));
	let showInputs  = $state(false);

	const DAY_PRESETS = [1, 2, 3, 5, 7, 10, 14, 21, 30, 60, 90];
	let durationDays = $state(7);
	let durationStart = $state('');

	function isoDate(d) { return d.toISOString().slice(0, 10); }

	function applyDuration() {
		if (!durationStart) return;
		const start = new Date(durationStart + 'T00:00:00');
		const end   = new Date(start);
		end.setDate(end.getDate() + durationDays);
		simRange = { start: isoDate(start), end: isoDate(end) };
	}

	$effect(() => { durationDays; durationStart; applyDuration(); });

	// ── create study from house ───────────────────────────────────────────────
	let createStudyLoading = $state(false);
	let createStudyError   = $state(null);

	async function createStudy() {
		if (!houseName) return;
		createStudyLoading = true;
		createStudyError   = null;
		try {
			const res = await fetch(`${API}/houses/${houseName}/studies`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ label: '' }),
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			const data = await res.json();
			await loadHouse(houseName);
			await openStudy(data.id);
			simPaneTab = 'sim';
		} catch (e) {
			createStudyError = e.message;
		} finally {
			createStudyLoading = false;
		}
	}

	// ── duplicate study ───────────────────────────────────────────────────────
	let dupSourceId    = $state(null);
	let dupDialogOpen  = $state(false);
	let dupLoading     = $state(false);
	let dupError       = $state(null);

	function openDupDialog(sourceId) {
		dupSourceId   = sourceId;
		dupError      = null;
		dupDialogOpen = true;
	}

	async function confirmDuplicate() {
		if (!houseName || !dupSourceId) return;
		dupLoading = true;
		dupError   = null;
		try {
			const res = await fetch(`${API}/houses/${houseName}/studies/${dupSourceId}/duplicate`, {
				method: 'POST',
			});
			if (!res.ok) {
				const d = await res.json().catch(() => ({}));
				throw new Error(d.detail ?? res.statusText);
			}
			const data = await res.json();
			dupDialogOpen = false;
			await loadHouse(houseName);
			await openStudy(data.id);
		} catch (e) {
			dupError = e.message;
		} finally {
			dupLoading = false;
		}
	}

	// ── param groups (identifiability) ───────────────────────────────────────
	let paramGroups = $state([]);

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
		} catch { /* silently ignore */ }
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
		await loadHousesList();
	});
</script>

<svelte:window onkeydown={onKeyDown} />

<!-- ── duplicate dialog ──────────────────────────────────────────────────── -->
{#if dupDialogOpen}
	<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
	<div class="dialog-backdrop" onclick={() => (dupDialogOpen = false)}>
		<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
		<div class="dialog" onclick={(e) => e.stopPropagation()}>
			<div class="dialog-title">Duplicate study</div>
			{#if dupError}<div class="dialog-error">{dupError}</div>{/if}
			<div class="dialog-actions">
				<button onclick={() => (dupDialogOpen = false)}>Cancel</button>
				<button class="primary" onclick={confirmDuplicate} disabled={dupLoading}>
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
			<button class="nav-item" class:active={activeSection === 'houses' || activeSection === 'house'} onclick={() => (activeSection = houseName ? 'house' : 'houses')}>
				House
			</button>

			<!-- house sub-nav -->
			{#if activeSection === 'house' && houseName}
				<div class="nav-divider"></div>
				<button class="nav-item nav-back" onclick={() => { houseName = null; house = null; selectedStudyId = null; model = null; activeSection = 'houses'; }}>← all houses</button>
			{/if}
		</div>
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

		{:else if activeSection === 'houses'}
			<!-- ── house picker ── -->
			<div class="home">
				<div class="home-header">
					{#if housesError}
						<span class="api-warn">⚠ API unreachable — {housesError}</span>
					{:else}
						<span class="home-title">Houses</span>
					{/if}
					<button class="home-new-btn" onclick={createNewHouse}>+ New house</button>
				</div>

				<div class="house-grid">
					{#each housesList as h}
						<div class="house-card" class:selected={h.name === houseName}>
							<button class="card-open" onclick={() => openHouse(h.name)}>
								<div class="card-label">{h.label ?? h.name}</div>
								<div class="card-name">{h.name}</div>
								<div class="card-meta">
									<span>{h.n_rooms} room{h.n_rooms !== 1 ? 's' : ''}</span>
									<span>·</span>
									<span>{h.n_elements} element{h.n_elements !== 1 ? 's' : ''}</span>
									<span>·</span>
									<span>{h.n_studies} stud{h.n_studies !== 1 ? 'ies' : 'y'}</span>
								</div>
								<div class="card-hash"># {h.model_hash}</div>
							</button>
						</div>
					{/each}

					{#if housesList.length === 0 && !housesError}
						<div class="card-empty">
							<span>No houses yet.<br/>Click "+ New house" to create one.</span>
						</div>
					{/if}
				</div>
			</div>

		{:else if activeSection === 'house' && house}
			<div class="house-split">
				<div class="house-pane">
					<HousePanel
						{house}
						onchange={(h) => (house = { ...h, _model_hash: house._model_hash, studies: $state.snapshot(house.studies) })}
						{customMaterials}
						dirty={houseDirty}
						saveLoading={houseSaveLoading}
						saveError={houseSaveError}
						onsave={saveHouse}
						oncreatestudy={createStudy}
						{createStudyLoading}
						{createStudyError}
						ondelete={deleteHouse}
					/>
				</div>
				<div class="study-pane">
					<div class="study-pane-tabs">
						<button class="sim-tab" class:active={simPaneTab === 'studies'}  onclick={() => (simPaneTab = 'studies')}>Studies</button>
						{#if selectedStudyId}
							<button class="sim-tab" class:active={simPaneTab === 'sim'}      onclick={() => (simPaneTab = 'sim')}>Simulation</button>
							<button class="sim-tab" class:active={simPaneTab === 'topology'} onclick={() => (simPaneTab = 'topology')}>Topology</button>
							<button class="sim-tab" class:active={simPaneTab === 'inputs'}   onclick={() => (simPaneTab = 'inputs')}>Inputs</button>
							<button class="sim-tab" class:active={simPaneTab === 'run'}      onclick={() => (simPaneTab = 'run')}>Run</button>
							<button class="sim-tab" class:active={simPaneTab === 'fit'}      onclick={() => (simPaneTab = 'fit')}>Fit</button>
							<button class="sim-tab sim-tab-dev" class:active={simPaneTab === 'rc'}    onclick={() => (simPaneTab = 'rc')}>RC</button>
							<button class="sim-tab sim-tab-dev" class:active={simPaneTab === 'debug'} onclick={() => (simPaneTab = 'debug')}>JSON</button>
						{/if}
					</div>

					<!-- study save bar (shown when a study is open) -->
					{#if selectedStudyId}
						<div class="study-save-bar">
							<button class="study-back-btn" onclick={() => { selectedStudyId = null; model = null; simPaneTab = 'studies'; }}>← studies</button>
							<span class="study-save-label">{selectedStudy?.label ?? selectedStudyId}</span>
							<button class="study-save-btn" class:dirty={studyDirty} onclick={saveStudy} disabled={saveLoading}>
								{saveLoading ? 'Saving…' : studyDirty ? 'Save ●' : 'Saved'}
							</button>
							{#if saveError}<span class="study-save-error">{saveError}</span>{/if}
						</div>
					{/if}

					{#if simPaneTab === 'studies'}
						<div class="studies-tab-content">
							<div class="studies-tab-header">
								{#if createStudyError}<div class="home-error">{createStudyError}</div>{/if}
								<button class="home-new-btn" onclick={createStudy} disabled={createStudyLoading}>
									{createStudyLoading ? 'Expanding…' : '+ New study'}
								</button>
							</div>
							<div class="study-grid">
								{#each studies as s}
									<div class="study-card" class:selected-card={s.id === selectedStudyId}>
										<button class="card-open" onclick={() => openStudy(s.id)}>
											<div class="card-label">{s.label ?? s.id}</div>
											<div class="card-uuid">{s.id}</div>
											{#if s._stale_run || s._stale_fit}
												<div class="card-stale">⚠ stale</div>
											{/if}
											{#if s.run}
												<div class="card-badge badge-run">run {s.run.timestamp?.slice(0,8) ?? ''}</div>
											{/if}
											{#if s.fit}
												<div class="card-badge badge-fit">fit {s.fit.timestamp?.slice(0,8) ?? ''}</div>
											{/if}
										</button>
										<div class="card-actions">
											<button class="card-action" onclick={() => openDupDialog(s.id)} title="Duplicate">⎘</button>
										</div>
									</div>
								{/each}

								{#if studies.length === 0}
									<div class="study-card card-empty">
										<span>No studies yet.<br/>Click "+ New study" to create one.</span>
									</div>
								{/if}
							</div>
						</div>

					{:else if simPaneTab === 'sim'}
						{#if createStudyLoading}
							<div class="study-pane-empty"><span>expanding…</span></div>
						{:else if createStudyError}
							<div class="study-pane-empty study-pane-error"><span>{createStudyError}</span></div>
						{:else if model}
							<!-- ── control bar ── -->
							<div class="sim-controls">
								<div class="sim-ctrl-row sim-ctrl-range">
									{#if rangeMode === 'dates'}
										<input class="ctrl-date" type="date"
											value={simRange.start}
											oninput={(e) => (simRange = { ...simRange, start: e.currentTarget.value })}
											title="Start"
										/>
										<span class="ctrl-range-sep">→</span>
										<input class="ctrl-date" type="date"
											value={simRange.end}
											oninput={(e) => (simRange = { ...simRange, end: e.currentTarget.value })}
											title="End"
										/>
										<button class="ctrl-mode-toggle" onclick={() => (rangeMode = 'duration')} title="Switch to duration mode">⇄</button>
									{:else}
										<input class="ctrl-date ctrl-date-start" type="date"
											bind:value={durationStart}
											title="Start"
										/>
										<div class="ctrl-presets">
											{#each DAY_PRESETS as d}
												<button class="ctrl-preset" class:active={durationDays === d} onclick={() => (durationDays = d)}>{d}d</button>
											{/each}
										</div>
										<input class="ctrl-date ctrl-date-end" type="date"
											value={simRange.end}
											readonly
											title="End (computed)"
										/>
										<button class="ctrl-mode-toggle" onclick={() => (rangeMode = 'dates')} title="Switch to start/end mode">⇄</button>
									{/if}
								</div>

								<div class="sim-ctrl-row">
									<label class="ctrl-radio"><input type="radio" bind:group={simSolver} value="ivp" /><span>IVP (BDF)</span></label>
									<label class="ctrl-radio"><input type="radio" bind:group={simSolver} value="zoh" /><span>ZOH</span></label>
								</div>

								<div class="sim-ctrl-row">
									<button class="ctrl-btn ctrl-btn-run" onclick={() => triggerRun?.()}>Run</button>
									<button class="ctrl-btn ctrl-btn-fit" disabled>Fit</button>
									<button class="ctrl-btn" class:active={showInputs} onclick={() => (showInputs = !showInputs)}>Show inputs</button>
								</div>
							</div>

							<div class="sim-pane-body scrollable">
								<SimulationRun
									{model}
									inputs={simInputs}
									range={simRange}
									observations={simObservations}
									bind:solver={simSolver}
									{simStale}
									{onRunSuccess}
									hideControls={true}
									onready={(fn) => (triggerRun = fn)}
								/>
							</div>
						{:else}
							<div class="study-pane-empty"><span>select a study first</span></div>
						{/if}

					{:else if simPaneTab === 'topology'}
						{#if model}
							<div class="body">
								<PropertiesPanel {model} {selected} {onpatch} {onadd} {ondelete} {ondeleteedge} />
								<GraphView {model} {selected} onselect={(s) => (selected = s)} {onaddedge} groups={paramGroups} />
							</div>
						{/if}

					{:else if simPaneTab === 'inputs'}
						{#if model}
							<div class="body scrollable">
								<InputsPanel {model} bind:inputs={simInputs} bind:range={simRange} bind:observations={simObservations} />
							</div>
						{/if}

					{:else if simPaneTab === 'run'}
						{#if model}
							<SimulationRun {model} inputs={simInputs} range={simRange} observations={simObservations} bind:solver={simSolver} {simStale} {onRunSuccess} />
						{/if}

					{:else if simPaneTab === 'fit'}
						{#if model}
							<FitPanel {model} inputs={simInputs} range={simRange} observations={simObservations} groups={paramGroups} />
						{/if}

					{:else if simPaneTab === 'rc'}
						{#if model}
							<div class="sim-pane-body">
								<GraphView {model} selected={null} onselect={() => {}} onaddedge={() => {}} groups={paramGroups} />
							</div>
						{:else}
							<div class="study-pane-empty"><span>no model</span></div>
						{/if}

					{:else if simPaneTab === 'debug'}
						<div class="debug-view">
							<pre>{JSON.stringify({ model, inputs: simInputs, range: simRange, solver: simSolver }, null, 2)}</pre>
						</div>
					{/if}
				</div>
			</div>

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

	.nav-house-name {
		font-size: 11px;
		font-weight: 600;
		color: #e2e8f0;
		padding: 0 16px 4px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
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

	/* ── house split view ── */
	.house-split {
		flex: 1;
		display: flex;
		min-height: 0;
		overflow: hidden;
	}

	.house-pane {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-width: 0;
		overflow: hidden;
		border-right: 1px solid #1e293b;
	}

	.study-pane {
		flex: 2;
		min-width: 0;
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
		background: #111827;
	}

	.study-pane-empty {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		color: #334155;
		font-size: 12px;
	}

	.study-pane-error { color: #f87171 !important; }

	.study-pane-tabs {
		display: flex;
		flex-shrink: 0;
		border-bottom: 1px solid #1e293b;
		background: #111827;
	}

	.sim-tab {
		flex: 1;
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		color: #64748b;
		font-size: 11px;
		font-weight: 500;
		padding: 7px 4px 5px;
		cursor: pointer;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		border-radius: 0;
		transition: color 0.1s, border-color 0.1s;
	}
	.sim-tab:hover  { color: #94a3b8; background: none; }
	.sim-tab.active { color: #e2e8f0; border-bottom-color: #3b82f6; }
	.sim-tab-dev    { color: #334155; font-style: italic; }
	.sim-tab-dev:hover { color: #64748b; }
	.sim-tab-dev.active { color: #94a3b8; border-bottom-color: #475569; }

	/* ── study save bar ── */
	.study-save-bar {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 5px 12px;
		border-bottom: 1px solid #1e293b;
		background: #0f172a;
		flex-shrink: 0;
	}

	.study-back-btn {
		background: none;
		border: none;
		color: #475569;
		font-size: 11px;
		padding: 2px 6px;
		cursor: pointer;
		border-radius: 3px;
		flex-shrink: 0;
	}
	.study-back-btn:hover { color: #94a3b8; background: #1e293b; }

	.study-save-label {
		flex: 1;
		font-size: 11px;
		font-weight: 600;
		color: #94a3b8;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.study-save-btn {
		background: none;
		border: 1px solid #334155;
		color: #475569;
		font-size: 11px;
		font-weight: 600;
		padding: 3px 10px;
		border-radius: 4px;
		cursor: pointer;
		flex-shrink: 0;
	}
	.study-save-btn:hover:not(:disabled) { background: #1e293b; color: #94a3b8; }
	.study-save-btn.dirty { border-color: #f59e0b; color: #fcd34d; }
	.study-save-btn:disabled { opacity: 0.4; cursor: default; }

	.study-save-error {
		font-size: 10px;
		color: #f87171;
		flex-shrink: 0;
	}

	.sim-pane-body {
		flex: 1;
		display: flex;
		flex-direction: column;
		min-height: 0;
		overflow: hidden;
	}
	.sim-pane-body.scrollable { overflow-y: auto; }

	/* ── simulation control bar ── */
	.sim-controls {
		display: flex;
		flex-direction: column;
		gap: 0;
		border-bottom: 1px solid #1e293b;
		flex-shrink: 0;
		background: #111827;
	}

	.sim-ctrl-row {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 7px 12px;
		border-bottom: 1px solid #0f172a;
	}
	.sim-ctrl-row:last-child { border-bottom: none; }

	.sim-ctrl-range {
		flex-wrap: wrap;
		gap: 5px;
	}

	.ctrl-date {
		background: #0f172a;
		color: #e2e8f0;
		border: 1px solid #334155;
		border-radius: 3px;
		padding: 4px 6px;
		font-size: 12px;
		font-family: monospace;
		flex: 1;
		min-width: 110px;
		color-scheme: dark;
	}
	.ctrl-date:focus         { outline: none; border-color: #6366f1; }
	.ctrl-date[readonly]     { color: #64748b; }

	.ctrl-range-sep {
		color: #475569;
		font-size: 12px;
		flex-shrink: 0;
	}

	.ctrl-presets {
		display: flex;
		flex-wrap: wrap;
		gap: 3px;
		flex: 1;
	}

	.ctrl-preset {
		background: #1e293b;
		border: 1px solid #334155;
		color: #64748b;
		font-size: 10px;
		font-family: monospace;
		padding: 3px 6px;
		border-radius: 3px;
		cursor: pointer;
		min-width: 28px;
		text-align: center;
	}
	.ctrl-preset:hover  { background: #273548; color: #94a3b8; }
	.ctrl-preset.active { background: #334155; color: #e2e8f0; border-color: #6366f1; }

	.ctrl-mode-toggle {
		background: none;
		border: 1px solid #334155;
		color: #475569;
		font-size: 13px;
		padding: 3px 7px;
		border-radius: 3px;
		cursor: pointer;
		flex-shrink: 0;
	}
	.ctrl-mode-toggle:hover { color: #94a3b8; background: #1e293b; }

	.ctrl-radio {
		display: flex;
		align-items: center;
		gap: 5px;
		cursor: pointer;
		margin-right: 6px;
	}
	.ctrl-radio span { font-size: 12px; color: #e2e8f0; }

	.ctrl-btn {
		font-size: 12px;
		font-weight: 600;
		padding: 5px 14px;
		border-radius: 4px;
		border: 1px solid #334155;
		background: #1e293b;
		color: #94a3b8;
		cursor: pointer;
	}
	.ctrl-btn:hover:not(:disabled) { background: #273548; color: #e2e8f0; }
	.ctrl-btn:disabled              { opacity: 0.35; cursor: default; }
	.ctrl-btn.active                { background: #334155; color: #e2e8f0; }

	.ctrl-btn-run {
		background: #4f46e5;
		border-color: #4338ca;
		color: #f1f5f9;
	}
	.ctrl-btn-run:hover { background: #4338ca; }

	.ctrl-btn-fit { color: #64748b; }

	/* ── studies tab (right pane) ── */
	.studies-tab-content {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 16px;
		overflow-y: auto;
	}

	.studies-tab-header {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 10px;
		flex-shrink: 0;
	}

	/* ── home views ── */
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

	.home-new-btn {
		background: #1e3a5f;
		color: #93c5fd;
		border: 1px solid #1e4976;
		border-radius: 4px;
		padding: 5px 12px;
		font-size: 12px;
		font-weight: 600;
		cursor: pointer;
	}
	.home-new-btn:hover:not(:disabled) { background: #1e4976; }
	.home-new-btn:disabled { opacity: 0.5; cursor: default; }

	.home-error {
		font-size: 12px;
		color: #f87171;
	}

	.api-warn { font-size: 13px; color: #f59e0b; }

	/* ── house grid ── */
	.house-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 12px;
	}

	.house-card {
		width: 220px;
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		transition: border-color 0.15s;
	}
	.house-card:hover { border-color: #475569; }
	.house-card.selected { border-color: #3b82f6; }

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

	.card-label {
		font-size: 13px;
		font-weight: 600;
		color: #e2e8f0;
	}

	.card-name {
		font-size: 10px;
		font-family: monospace;
		color: #64748b;
	}

	.card-meta {
		display: flex;
		gap: 4px;
		font-size: 11px;
		color: #94a3b8;
		flex-wrap: wrap;
	}

	.card-hash {
		font-size: 9px;
		font-family: monospace;
		color: #475569;
	}

	/* ── study grid ── */
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
	.study-card.selected-card { border-color: #3b82f6; }

	.card-uuid {
		font-size: 10px;
		font-family: monospace;
		color: #64748b;
		word-break: break-all;
	}

	.card-stale {
		font-size: 10px;
		color: #f59e0b;
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
	.badge-run { background: #1e3a5f; color: #93c5fd; }
	.badge-fit { background: #14532d; color: #86efac; }

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

	.dialog-error { font-size: 12px; color: #f87171; }

	.dialog-actions {
		display: flex;
		justify-content: flex-end;
		gap: 8px;
	}
</style>
