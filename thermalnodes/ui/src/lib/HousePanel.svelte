<script>
  let { house, onchange, customMaterials = {} } = $props();

  const BUILTIN_MATERIALS = {
    brick_full:     { lambda: 0.8,   rho: 1800, cp: 840,  name: 'Brique pleine' },
    brick_hollow:   { lambda: 0.45,  rho: 1200, cp: 840,  name: 'Brique creuse' },
    stone_calcaire: { lambda: 1.7,   rho: 2200, cp: 900,  name: 'Calcaire' },
    stone_rubble:   { lambda: 1.3,   rho: 2000, cp: 900,  name: 'Moellon' },
    concrete_heavy: { lambda: 1.75,  rho: 2300, cp: 840,  name: 'Béton lourd' },
    concrete_slab:  { lambda: 1.65,  rho: 2200, cp: 840,  name: 'Dalle béton' },
    glass_wool:     { lambda: 0.035, rho: 15,   cp: 840,  name: 'Laine de verre' },
    rock_wool:      { lambda: 0.038, rho: 30,   cp: 840,  name: 'Laine de roche' },
    cellulose:      { lambda: 0.040, rho: 50,   cp: 1900, name: 'Ouate de cellulose' },
    plaster:        { lambda: 0.57,  rho: 1200, cp: 1000, name: 'Plâtre' },
    lime_plaster:   { lambda: 0.87,  rho: 1600, cp: 1000, name: 'Enduit chaux' },
    wood_frame:     { lambda: 0.13,  rho: 530,  cp: 1600, name: 'Bois (structure)' },
    wood_floor:     { lambda: 0.16,  rho: 700,  cp: 1600, name: 'Parquet' },
    tile_clay:      { lambda: 1.0,   rho: 1900, cp: 840,  name: 'Tuile terre cuite' },
  };

  const ORIENTATIONS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  const WEATHER_SOURCES = ['open_meteo'];

  // ── derived ───────────────────────────────────────────────────────────────
  const rooms    = $derived(house?.rooms    ?? []);
  const elements = $derived(house?.elements ?? []);
  const materials = $derived({ ...BUILTIN_MATERIALS, ...(customMaterials ?? {}), ...(house?.materials ?? {}) });

  const outdoorEl = $derived(elements.find(e => e.kind === 'outdoor') ?? null);

  // zones available for the "between" dropdowns
  const zoneOptions = $derived([
    ...rooms.map(r => r.id),
    'outdoor',
    'ground',
  ]);

  // ── patch helpers ─────────────────────────────────────────────────────────
  function patchHouse(patch) {
    onchange({ ...house, ...patch });
  }

  function patchRoom(id, patch) {
    patchHouse({ rooms: rooms.map(r => r.id === id ? { ...r, ...patch } : r) });
  }

  function patchElement(id, patch) {
    patchHouse({ elements: elements.map(el => el.id === id ? { ...el, ...patch } : el) });
  }

  function patchOutdoor(patch) {
    if (outdoorEl) {
      patchElement('outdoor', patch);
    } else {
      patchHouse({ elements: [...elements, { id: 'outdoor', kind: 'outdoor', ...patch }] });
    }
  }

  function patchOutdoorLocation(patch) {
    const loc = { ...(outdoorEl?.location ?? {}), ...patch };
    patchOutdoor({ location: loc });
  }

  function deleteRoom(id) {
    patchHouse({
      rooms:    rooms.filter(r => r.id !== id),
      elements: elements.filter(el => !el.between?.includes(id)),
    });
  }

  function deleteElement(id) {
    patchHouse({ elements: elements.filter(el => el.id !== id) });
  }

  // ── layer helpers ─────────────────────────────────────────────────────────
  function patchLayer(elId, idx, patch) {
    patchHouse({ elements: elements.map(el => {
      if (el.id !== elId) return el;
      return { ...el, layers: el.layers.map((l, i) => i === idx ? { ...l, ...patch } : l) };
    })});
  }

  function addLayer(elId) {
    patchHouse({ elements: elements.map(el => {
      if (el.id !== elId) return el;
      return { ...el, layers: [...el.layers, { material: 'plaster', thickness: 0.01 }] };
    })});
  }

  function deleteLayer(elId, idx) {
    patchHouse({ elements: elements.map(el => {
      if (el.id !== elId) return el;
      return { ...el, layers: el.layers.filter((_, i) => i !== idx) };
    })});
  }

  // ── expanded row ──────────────────────────────────────────────────────────
  let expandedId = $state(null);  // room id, element id, or 'outdoor'

  function toggleExpand(id) {
    expandedId = expandedId === id ? null : id;
  }

  // ── add room ──────────────────────────────────────────────────────────────
  let newRoomId    = $state('');
  let newRoomError = $state('');

  function addRoom() {
    const id = newRoomId.trim();
    if (!id) { newRoomError = 'ID required'; return; }
    if (rooms.some(r => r.id === id)) { newRoomError = 'ID already used'; return; }
    patchHouse({ rooms: [...rooms, { id, a: 4, b: 4, c: 2.5 }] });
    newRoomId = '';
    newRoomError = '';
    expandedId = id;
  }

  // ── add element ───────────────────────────────────────────────────────────
  let showAddForm = $state(false);
  let newKind     = $state('opaque');
  let newId       = $state('');
  let newBetween0 = $state('');
  let newBetween1 = $state('outdoor');
  let newA        = $state(4.0);
  let newB        = $state(2.5);
  let newOri      = $state('S');
  let newTilt     = $state(90);
  let newMat      = $state('brick_full');
  let newThick    = $state(0.2);
  let newU        = $state(2.8);
  let newSHGC     = $state(0.67);
  let newAch      = $state(0.4);
  let newElError  = $state('');

  $effect(() => {
    // default between[0] to first room when rooms change
    if (newBetween0 === '' && rooms.length > 0) newBetween0 = rooms[0].id;
  });

  function addElement() {
    const id = newId.trim() || `${newKind}_${elements.length + 1}`;
    if (elements.some(e => e.id === id)) { newElError = 'ID already used'; return; }
    if (!newBetween0) { newElError = 'Select a room for "from"'; return; }

    let el;
    if (newKind === 'opaque') {
      el = { id, kind: 'opaque', between: [newBetween0, newBetween1],
             a: newA, b: newB, orientation: newOri, tilt: newTilt,
             layers: [{ material: newMat, thickness: newThick }] };
    } else if (newKind === 'glazing') {
      el = { id, kind: 'glazing', between: [newBetween0, newBetween1],
             a: newA, b: newB, orientation: newOri, tilt: 90,
             U: newU, SHGC: newSHGC };
    } else {
      el = { id, kind: 'air_exchange', between: [newBetween0, newBetween1], ach: newAch };
    }
    patchHouse({ elements: [...elements, el] });
    newId = '';
    newElError = '';
    showAddForm = false;
    expandedId = id;
  }

  // ── flat ordered list: rooms first, then non-outdoor elements, then outdoor ─
  const flatItems = $derived([
    ...rooms.map(r => ({ _type: 'room', ...r })),
    ...elements.filter(e => e.kind !== 'outdoor'),
    ...(outdoorEl ? [outdoorEl] : [{ id: 'outdoor', kind: 'outdoor' }]),
  ]);
</script>

<div class="house-panel">

  <!-- ── flat list ──────────────────────────────────────────────────────────── -->
  <div class="list">
    {#each flatItems as item (item.id)}
      {@const isRoom = item._type === 'room'}
      {@const isOutdoor = item.kind === 'outdoor'}
      {@const expanded = expandedId === item.id}

      <div class="row" class:expanded class:row-room={isRoom} class:row-outdoor={isOutdoor}>

        <!-- ── row header ── -->
        <div class="row-header">
          <span class="kind-badge kind-{isRoom ? 'room' : item.kind}">{isRoom ? 'room' : item.kind}</span>
          <span class="row-id">{item.id}</span>

          <!-- summary chips -->
          {#if isRoom}
            <span class="summary">{item.a ?? '?'} × {item.b ?? '?'} × {item.c ?? '?'} m</span>
          {:else if item.kind === 'opaque'}
            <span class="summary">{item.between?.[0]} ↔ {item.between?.[1]}</span>
            <span class="summary">{item.orientation ?? '—'} · {((item.a ?? 0)*(item.b ?? 0)).toFixed(1)} m²</span>
          {:else if item.kind === 'glazing'}
            <span class="summary">{item.between?.[0]} ↔ {item.between?.[1]}</span>
            <span class="summary">U={item.U} · {((item.a ?? 0)*(item.b ?? 0)).toFixed(2)} m²</span>
          {:else if item.kind === 'air_exchange'}
            <span class="summary">{item.between?.[0]} ↔ {item.between?.[1]}</span>
            <span class="summary">{item.ach} ACH</span>
          {:else if isOutdoor}
            <span class="summary">{item.location?.label ?? '—'} · {item.location?.lat ?? '?'},{item.location?.lon ?? '?'}</span>
            <span class="summary">{item.weather_source ?? '—'}</span>
          {/if}

          <span class="row-spacer"></span>
          <button class="icon-btn" onclick={() => toggleExpand(item.id)} title="Edit">
            {expanded ? '▲' : '▼'}
          </button>
          {#if !isOutdoor}
            <button class="icon-btn del-btn" onclick={() => isRoom ? deleteRoom(item.id) : deleteElement(item.id)} title="Delete">×</button>
          {/if}
        </div>

        <!-- ── inline editor ── -->
        {#if expanded}
          <div class="row-editor">

            {#if isRoom}
              <div class="field-row">
                <label class="field">
                  <span>a (m)</span>
                  <input type="number" value={item.a} min="0.1" step="0.5"
                    oninput={(e) => patchRoom(item.id, { a: parseFloat(e.target.value) || 0 })} />
                </label>
                <label class="field">
                  <span>b (m)</span>
                  <input type="number" value={item.b} min="0.1" step="0.5"
                    oninput={(e) => patchRoom(item.id, { b: parseFloat(e.target.value) || 0 })} />
                </label>
                <label class="field">
                  <span>c (m)</span>
                  <input type="number" value={item.c} min="0.1" step="0.1"
                    oninput={(e) => patchRoom(item.id, { c: parseFloat(e.target.value) || 0 })} />
                </label>
                <div class="field">
                  <span>volume</span>
                  <span class="computed-val">{((item.a ?? 0)*(item.b ?? 0)*(item.c ?? 0)).toFixed(1)} m³</span>
                </div>
                <label class="field">
                  <span>furniture factor</span>
                  <input type="number" value={item.furniture_factor ?? 2.5} min="1" step="0.5"
                    oninput={(e) => patchRoom(item.id, { furniture_factor: parseFloat(e.target.value) || 1 })} />
                </label>
              </div>

            {:else if item.kind === 'opaque'}
              <div class="field-row">
                <label class="field">
                  <span>from</span>
                  <select value={item.between?.[0]}
                    onchange={(e) => patchElement(item.id, { between: [e.target.value, item.between[1]] })}>
                    {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>to</span>
                  <select value={item.between?.[1]}
                    onchange={(e) => patchElement(item.id, { between: [item.between[0], e.target.value] })}>
                    {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>a (m)</span>
                  <input type="number" value={item.a} min="0.1" step="0.1"
                    oninput={(e) => patchElement(item.id, { a: parseFloat(e.target.value) || 0 })} />
                </label>
                <label class="field">
                  <span>b (m)</span>
                  <input type="number" value={item.b} min="0.1" step="0.1"
                    oninput={(e) => patchElement(item.id, { b: parseFloat(e.target.value) || 0 })} />
                </label>
                <div class="field">
                  <span>area</span>
                  <span class="computed-val">{((item.a ?? 0)*(item.b ?? 0)).toFixed(2)} m²</span>
                </div>
                <label class="field">
                  <span>orientation</span>
                  <select value={item.orientation ?? 'S'}
                    onchange={(e) => patchElement(item.id, { orientation: e.target.value })}>
                    {#each ORIENTATIONS as o}<option value={o}>{o}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>tilt (°)</span>
                  <input type="number" value={item.tilt ?? 90} min="0" max="90" step="5"
                    oninput={(e) => patchElement(item.id, { tilt: parseFloat(e.target.value) || 90 })} />
                </label>
              </div>
              <div class="layers-section">
                <div class="layers-title">Layers (interior → exterior)</div>
                {#each item.layers ?? [] as layer, i}
                  <div class="layer-row">
                    <span class="layer-num">{i + 1}</span>
                    <label class="field">
                      <span>material</span>
                      <select value={layer.material}
                        onchange={(e) => patchLayer(item.id, i, { material: e.target.value })}>
                        {#each Object.entries(materials) as [id, m]}
                          <option value={id}>{m.name ?? id}</option>
                        {/each}
                      </select>
                    </label>
                    <label class="field">
                      <span>thickness (m)</span>
                      <input type="number" value={layer.thickness} min="0.001" step="0.01"
                        oninput={(e) => patchLayer(item.id, i, { thickness: parseFloat(e.target.value) || 0.01 })} />
                    </label>
                    <button class="icon-btn del-btn" onclick={() => deleteLayer(item.id, i)} title="Remove">×</button>
                  </div>
                {/each}
                <button class="add-layer-btn" onclick={() => addLayer(item.id)}>+ Layer</button>
              </div>

            {:else if item.kind === 'glazing'}
              <div class="field-row">
                <label class="field">
                  <span>from</span>
                  <select value={item.between?.[0]}
                    onchange={(e) => patchElement(item.id, { between: [e.target.value, item.between[1]] })}>
                    {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>to</span>
                  <select value={item.between?.[1]}
                    onchange={(e) => patchElement(item.id, { between: [item.between[0], e.target.value] })}>
                    {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>a (m)</span>
                  <input type="number" value={item.a} min="0.1" step="0.1"
                    oninput={(e) => patchElement(item.id, { a: parseFloat(e.target.value) || 0 })} />
                </label>
                <label class="field">
                  <span>b (m)</span>
                  <input type="number" value={item.b} min="0.1" step="0.1"
                    oninput={(e) => patchElement(item.id, { b: parseFloat(e.target.value) || 0 })} />
                </label>
                <div class="field">
                  <span>area</span>
                  <span class="computed-val">{((item.a ?? 0)*(item.b ?? 0)).toFixed(2)} m²</span>
                </div>
                <label class="field">
                  <span>orientation</span>
                  <select value={item.orientation ?? 'S'}
                    onchange={(e) => patchElement(item.id, { orientation: e.target.value })}>
                    {#each ORIENTATIONS as o}<option value={o}>{o}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>U (W/m²K)</span>
                  <input type="number" value={item.U} min="0.1" step="0.1"
                    oninput={(e) => patchElement(item.id, { U: parseFloat(e.target.value) || 0 })} />
                </label>
                <label class="field">
                  <span>SHGC</span>
                  <input type="number" value={item.SHGC} min="0" max="1" step="0.01"
                    oninput={(e) => patchElement(item.id, { SHGC: parseFloat(e.target.value) || 0 })} />
                </label>
              </div>

            {:else if item.kind === 'air_exchange'}
              <div class="field-row">
                <label class="field">
                  <span>from</span>
                  <select value={item.between?.[0]}
                    onchange={(e) => patchElement(item.id, { between: [e.target.value, item.between[1]] })}>
                    {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>to</span>
                  <select value={item.between?.[1]}
                    onchange={(e) => patchElement(item.id, { between: [item.between[0], e.target.value] })}>
                    {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
                  </select>
                </label>
                <label class="field">
                  <span>ACH (h⁻¹)</span>
                  <input type="number" value={item.ach} min="0.01" step="0.1"
                    oninput={(e) => patchElement(item.id, { ach: parseFloat(e.target.value) || 0 })} />
                </label>
              </div>

            {:else if isOutdoor}
              <div class="field-row">
                <label class="field">
                  <span>label</span>
                  <input type="text" value={item.location?.label ?? ''}
                    oninput={(e) => patchOutdoorLocation({ label: e.target.value })} />
                </label>
                <label class="field">
                  <span>lat</span>
                  <input type="number" value={item.location?.lat ?? ''} step="0.01"
                    oninput={(e) => patchOutdoorLocation({ lat: parseFloat(e.target.value) })} />
                </label>
                <label class="field">
                  <span>lon</span>
                  <input type="number" value={item.location?.lon ?? ''} step="0.01"
                    oninput={(e) => patchOutdoorLocation({ lon: parseFloat(e.target.value) })} />
                </label>
                <label class="field">
                  <span>weather source</span>
                  <select value={item.weather_source ?? 'open_meteo'}
                    onchange={(e) => patchOutdoor({ weather_source: e.target.value })}>
                    {#each WEATHER_SOURCES as s}<option value={s}>{s}</option>{/each}
                  </select>
                </label>
              </div>
            {/if}

          </div>
        {/if}
      </div>
    {/each}
  </div>

  <!-- ── add area ───────────────────────────────────────────────────────────── -->
  <div class="add-area">

    <!-- add room (always visible, compact) -->
    <div class="add-room-inline">
      <span class="add-label">Add room</span>
      <input type="text" bind:value={newRoomId} placeholder="id, e.g. salon"
        onkeydown={(e) => e.key === 'Enter' && addRoom()} />
      {#if newRoomError}<span class="field-error">{newRoomError}</span>{/if}
      <button onclick={addRoom}>Add room</button>
    </div>

    <!-- add element toggle -->
    <button class="add-el-toggle" onclick={() => { showAddForm = !showAddForm; newElError = ''; }}>
      {showAddForm ? '▲ Cancel' : '+ Add element'}
    </button>

    {#if showAddForm}
      <div class="add-el-form">
        <div class="kind-tabs">
          {#each ['opaque', 'glazing', 'air_exchange'] as k}
            <button class="kind-tab" class:active={newKind === k} onclick={() => newKind = k}>{k}</button>
          {/each}
        </div>

        <div class="field-row">
          <label class="field">
            <span>id (opt.)</span>
            <input type="text" bind:value={newId} placeholder="auto" />
          </label>
          <label class="field">
            <span>from</span>
            <select bind:value={newBetween0}>
              {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
            </select>
          </label>
          <label class="field">
            <span>to</span>
            <select bind:value={newBetween1}>
              {#each zoneOptions as z}<option value={z}>{z}</option>{/each}
            </select>
          </label>

          {#if newKind === 'opaque' || newKind === 'glazing'}
            <label class="field">
              <span>a (m)</span>
              <input type="number" bind:value={newA} min="0.1" step="0.1" />
            </label>
            <label class="field">
              <span>b (m)</span>
              <input type="number" bind:value={newB} min="0.1" step="0.1" />
            </label>
            <label class="field">
              <span>orientation</span>
              <select bind:value={newOri}>
                {#each ORIENTATIONS as o}<option value={o}>{o}</option>{/each}
              </select>
            </label>
          {/if}

          {#if newKind === 'opaque'}
            <label class="field">
              <span>tilt (°)</span>
              <input type="number" bind:value={newTilt} min="0" max="90" step="5" />
            </label>
            <label class="field">
              <span>material</span>
              <select bind:value={newMat}>
                {#each Object.entries(materials) as [id, m]}
                  <option value={id}>{m.name ?? id}</option>
                {/each}
              </select>
            </label>
            <label class="field">
              <span>thickness (m)</span>
              <input type="number" bind:value={newThick} min="0.01" step="0.05" />
            </label>
          {:else if newKind === 'glazing'}
            <label class="field">
              <span>U (W/m²K)</span>
              <input type="number" bind:value={newU} min="0.1" step="0.1" />
            </label>
            <label class="field">
              <span>SHGC</span>
              <input type="number" bind:value={newSHGC} min="0" max="1" step="0.01" />
            </label>
          {:else if newKind === 'air_exchange'}
            <label class="field">
              <span>ACH (h⁻¹)</span>
              <input type="number" bind:value={newAch} min="0.01" step="0.1" />
            </label>
          {/if}
        </div>

        {#if newElError}<div class="field-error">{newElError}</div>{/if}
        <button class="add-btn" onclick={addElement}>Add</button>
      </div>
    {/if}
  </div>

</div>

<style>
  .house-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }

  /* ── flat list ── */
  .list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 12px 16px;
  }

  .row {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    overflow: hidden;
  }
  .row.expanded       { border-color: #6366f1; }
  .row.row-room       { border-left: 3px solid #6366f1; }
  .row.row-outdoor    { border-left: 3px solid #0ea5e9; }

  .row-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 10px;
  }

  .row-id {
    font-size: 12px;
    font-family: monospace;
    font-weight: 600;
    color: #e2e8f0;
    flex-shrink: 0;
  }

  .summary {
    font-size: 11px;
    color: #64748b;
    font-family: monospace;
    white-space: nowrap;
  }

  .row-spacer { flex: 1; }

  .row-editor {
    border-top: 1px solid #334155;
    padding: 12px;
    background: #0f172a;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  /* ── layers ── */
  .layers-section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .layers-title {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #94a3b8;
  }
  .layer-row {
    display: flex;
    align-items: flex-end;
    gap: 8px;
  }
  .layer-num {
    font-size: 10px;
    color: #64748b;
    font-family: monospace;
    padding-bottom: 6px;
    flex-shrink: 0;
  }
  .add-layer-btn {
    align-self: flex-start;
    font-size: 11px;
    padding: 3px 8px;
  }

  /* ── add area ── */
  .add-area {
    border-top: 1px solid #334155;
    padding: 10px 16px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex-shrink: 0;
    background: #1e293b;
  }

  .add-room-inline {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .add-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    flex-shrink: 0;
  }

  .add-room-inline input {
    width: 140px;
  }

  .add-el-toggle {
    align-self: flex-start;
    font-size: 11px;
    padding: 4px 10px;
    background: #0f172a;
    color: #94a3b8;
    border: 1px solid #334155;
  }
  .add-el-toggle:hover { background: #1e293b; color: #e2e8f0; }

  .add-el-form {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .kind-tabs {
    display: flex;
    gap: 4px;
  }
  .kind-tab {
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 4px;
    background: #0f172a;
    color: #94a3b8;
    border: 1px solid #334155;
  }
  .kind-tab:hover  { background: #1e293b; color: #e2e8f0; }
  .kind-tab.active { background: #312e81; color: #a5b4fc; border-color: #6366f1; }

  .add-btn {
    align-self: flex-start;
    background: #312e81;
    color: #a5b4fc;
    border: 1px solid #6366f1;
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 12px;
    cursor: pointer;
  }
  .add-btn:hover { background: #3730a3; }

  /* ── shared form helpers ── */
  .field-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 80px;
  }
  .field > span {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #94a3b8;
    white-space: nowrap;
  }

  input, select {
    background: #0f172a;
    color: #e2e8f0;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 12px;
    font-family: monospace;
    width: 100%;
    box-sizing: border-box;
  }
  input:focus, select:focus { outline: none; border-color: #6366f1; }

  .computed-val {
    font-size: 12px;
    font-family: monospace;
    color: #94a3b8;
    padding: 4px 6px;
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 4px;
  }

  .field-error {
    font-size: 11px;
    color: #f87171;
  }

  .icon-btn {
    background: transparent;
    border: none;
    color: #94a3b8;
    font-size: 14px;
    line-height: 1;
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .icon-btn:hover  { background: #334155; color: #f1f5f9; }
  .del-btn:hover   { color: #ef4444; }

  /* ── kind badges ── */
  .kind-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 2px 6px;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .kind-room         { background: #312e81; color: #a5b4fc; }
  .kind-opaque       { background: #1e3a5f; color: #93c5fd; }
  .kind-glazing      { background: #14532d; color: #86efac; }
  .kind-air_exchange { background: #451a03; color: #fcd34d; }
  .kind-outdoor      { background: #0c4a6e; color: #7dd3fc; }
</style>
