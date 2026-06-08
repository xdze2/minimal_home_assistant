<script>
  let { house, onchange, customMaterials = {}, dirty = false, saveLoading = false, saveError = null, onsave = null, oncreatestudy = null } = $props();

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

  const zoneOptions = $derived([
    ...rooms.map(r => r.id),
    'outdoor',
    'ground',
  ]);

  // ── key figures (client-side computed) ───────────────────────────────────
  function roomVolume(r) {
    return (r.a ?? 0) * (r.b ?? 0) * (r.c ?? 0);
  }

  function opaqueUA(el) {
    const area = (el.a ?? 0) * (el.b ?? 0);
    const R = (el.layers ?? []).reduce((acc, l) => {
      const mat = materials[l.material];
      return acc + (mat ? (l.thickness / mat.lambda) : 0);
    }, 0.13 + 0.04); // h_i + h_e defaults
    return R > 0 ? area / R : null;
  }

  function keyFigures(item) {
    if (item._type === 'room') {
      const vol = roomVolume(item);
      return vol > 0 ? `${vol.toFixed(0)} m³` : null;
    }
    if (item.kind === 'opaque') {
      const area = (item.a ?? 0) * (item.b ?? 0);
      const ua = opaqueUA(item);
      return ua != null ? `${area.toFixed(1)} m²  ·  UA ${ua.toFixed(1)} W/K` : `${area.toFixed(1)} m²`;
    }
    if (item.kind === 'glazing') {
      const area = (item.a ?? 0) * (item.b ?? 0);
      const ua = item.U != null ? item.U * area : null;
      return ua != null ? `${area.toFixed(2)} m²  ·  UA ${ua.toFixed(1)} W/K` : `${area.toFixed(2)} m²`;
    }
    if (item.kind === 'air_exchange') {
      return item.ach != null ? `${item.ach} ACH` : null;
    }
    if (item.kind === 'outdoor') {
      return item.location?.label ?? null;
    }
    return null;
  }

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
  let expandedId = $state(null);

  // ── selection (for study) ─────────────────────────────────────────────────
  let selected = $state(/** @type {Set<string>} */ (new Set()));

  function toggleSelected(id) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    selected = next;
  }

  function toggleExpand(id) {
    expandedId = expandedId === id ? null : id;
  }

  // ── add element helpers ───────────────────────────────────────────────────
  let newKind     = $state(/** @type {string|null} */ (null)); // null = toolbar hidden
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
    if (newBetween0 === '' && rooms.length > 0) newBetween0 = rooms[0].id;
  });

  function openAddForm(kind) {
    newKind = newKind === kind ? null : kind;
    newElError = '';
    newId = '';
  }

  function addRoom() {
    const id = newId.trim() || `room_${rooms.length + 1}`;
    if (rooms.some(r => r.id === id)) { newElError = 'ID already used'; return; }
    patchHouse({ rooms: [...rooms, { id, a: 4, b: 4, c: 2.5 }] });
    newKind = null;
    newId = '';
    newElError = '';
    expandedId = id;
  }

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
    newKind = null;
    newId = '';
    newElError = '';
    expandedId = id;
  }

  function confirmAdd() {
    if (newKind === 'room') addRoom();
    else addElement();
  }

  // ── flat ordered list ─────────────────────────────────────────────────────
  const flatItems = $derived([
    ...rooms.map(r => ({ _type: 'room', ...r })),
    ...elements.filter(e => e.kind !== 'outdoor'),
    ...(outdoorEl ? [outdoorEl] : [{ id: 'outdoor', kind: 'outdoor' }]),
  ]);

  // ── kind metadata ─────────────────────────────────────────────────────────
  const KIND_META = {
    room:         { icon: '⬜', label: 'room',     color: 'room' },
    opaque:       { icon: '▬',  label: 'wall',     color: 'opaque' },
    glazing:      { icon: '◻',  label: 'window',   color: 'glazing' },
    air_exchange: { icon: '≋',  label: 'air exch', color: 'air_exchange' },
    outdoor:      { icon: '☁',  label: 'outdoor',  color: 'outdoor' },
  };

  function itemKind(item) {
    return item._type === 'room' ? 'room' : item.kind;
  }

  function connectivity(item) {
    if (item._type === 'room') return null;
    if (item.kind === 'outdoor') return null;
    const [a, b] = item.between ?? [];
    return a && b ? `${a} ↔ ${b}` : null;
  }
</script>

<div class="house-panel">

  <!-- ── toolbar ───────────────────────────────────────────────────────────── -->
  <div class="toolbar">
    <span class="toolbar-label">Add</span>
    {#each [
      { kind: 'room',         icon: '⬜', tip: 'Add room' },
      { kind: 'opaque',       icon: '▬',  tip: 'Add wall / roof / floor' },
      { kind: 'glazing',      icon: '◻',  tip: 'Add window / door' },
      { kind: 'air_exchange', icon: '≋',  tip: 'Add air exchange' },
    ] as btn}
      <button
        class="toolbar-btn kind-btn-{btn.kind}"
        class:active={newKind === btn.kind}
        onclick={() => openAddForm(btn.kind)}
        title={btn.tip}
      >
        <span class="tb-icon">{btn.icon}</span>
        <span class="tb-text">{btn.tip.replace('Add ', '')}</span>
      </button>
    {/each}

    <div class="toolbar-sep"></div>
    {#if onsave}
      {#if saveError}<span class="toolbar-save-error">{saveError}</span>{/if}
      <button class="toolbar-save" class:dirty onclick={onsave} disabled={saveLoading}>
        {saveLoading ? 'Saving…' : dirty ? 'Save ●' : 'Save'}
      </button>
    {/if}
    {#if oncreatestudy}
      <button class="toolbar-create" onclick={() => oncreatestudy(Array.from(selected))}>
        Create study
      </button>
    {/if}
  </div>

  <!-- ── inline add form ───────────────────────────────────────────────────── -->
  {#if newKind}
    <div class="add-form">
      <div class="field-row">
        <label class="field">
          <span>label (opt.)</span>
          <input type="text" bind:value={newId} placeholder="auto" />
        </label>

        {#if newKind !== 'room'}
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
        {/if}

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
      <div class="add-form-actions">
        <button class="add-confirm-btn" onclick={confirmAdd}>Add {newKind}</button>
        <button class="add-cancel-btn" onclick={() => { newKind = null; newElError = ''; }}>Cancel</button>
      </div>
    </div>
  {/if}

  <!-- ── grid header ────────────────────────────────────────────────────────── -->
  <div class="grid-header">
    <span></span>
    <span>label</span>
    <span>connectivity</span>
    <span>key figures</span>
    <span class="col-include">include</span>
    <span></span>
  </div>

  <!-- ── flat list ──────────────────────────────────────────────────────────── -->
  <div class="list">
    {#each flatItems as item (item.id)}
      {@const kind = itemKind(item)}
      {@const meta = KIND_META[kind]}
      {@const expanded = expandedId === item.id}
      {@const isOutdoor = kind === 'outdoor'}
      {@const conn = connectivity(item)}
      {@const figures = keyFigures(item)}

      <div class="row" class:expanded>

        <!-- ── row header (grid row) ── -->
        <div class="row-header" role="button" tabindex="0"
          onclick={() => toggleExpand(item.id)}
          onkeydown={(e) => e.key === 'Enter' && toggleExpand(item.id)}>
          <span class="kind-icon kind-{kind}" title={meta.label}>{meta.icon}</span>
          <span class="row-id">{item.id}</span>
          <span class="row-conn">{conn ?? ''}</span>
          <span class="row-figures">{figures ?? ''}</span>
          <span class="col-include" onclick={(e) => e.stopPropagation()}>
            {#if !isOutdoor}
              <input type="checkbox" checked={selected.has(item.id)}
                onchange={() => toggleSelected(item.id)} />
            {/if}
          </span>
          <span class="row-chevron">{expanded ? '▲' : '▼'}</span>
        </div>

        <!-- ── inline editor ── -->
        {#if expanded}
          <div class="row-editor">

            {#if kind === 'room'}
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
                    <div class="field">
                      <span>UA</span>
                      <span class="computed-val">
                        {(() => { const ua = opaqueUA(item); return ua != null ? ua.toFixed(2) + ' W/K' : '—'; })()}
                      </span>
                    </div>
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

            {#if !isOutdoor}
              <div class="editor-footer">
                <button class="delete-btn"
                  onclick={() => kind === 'room' ? deleteRoom(item.id) : deleteElement(item.id)}>
                  Delete
                </button>
              </div>
            {/if}

          </div>
        {/if}
      </div>
    {/each}
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

  /* ── toolbar ── */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border-bottom: 1px solid #1e293b;
    flex-shrink: 0;
  }

  .toolbar-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #475569;
    margin-right: 4px;
    flex-shrink: 0;
  }

  .toolbar-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 5px;
    border: 1px solid #334155;
    background: #1e293b;
    color: #94a3b8;
    font-size: 12px;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
  }
  .toolbar-btn:hover { background: #273548; color: #e2e8f0; }
  .toolbar-btn.active { background: #312e81; border-color: #6366f1; color: #a5b4fc; }

  .kind-btn-opaque.active       { background: #1e3a5f; border-color: #3b82f6; color: #93c5fd; }
  .kind-btn-glazing.active      { background: #14532d; border-color: #22c55e; color: #86efac; }
  .kind-btn-air_exchange.active { background: #451a03; border-color: #f59e0b; color: #fcd34d; }

  .tb-icon { font-size: 14px; line-height: 1; }
  .tb-text { font-size: 11px; }

  .toolbar-sep {
    flex: 1;
  }

  .toolbar-save {
    padding: 4px 12px;
    border-radius: 5px;
    border: 1px solid #334155;
    background: #1e293b;
    color: #64748b;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .toolbar-save:hover { background: #273548; color: #94a3b8; }
  .toolbar-save.dirty { border-color: #f59e0b; color: #fcd34d; background: #1c1a07; }
  .toolbar-save.dirty:hover { background: #2a2506; }
  .toolbar-save:disabled { opacity: 0.5; cursor: default; }

  .toolbar-save-error {
    font-size: 10px;
    color: #f87171;
  }

  .toolbar-create {
    padding: 4px 12px;
    border-radius: 5px;
    border: 1px solid #166534;
    background: #14532d;
    color: #86efac;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .toolbar-create:hover { background: #15803d; }

  /* ── add form ── */
  .add-form {
    padding: 10px 14px 12px;
    border-bottom: 1px solid #334155;
    background: #0f172a;
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex-shrink: 0;
  }

  .add-form-actions {
    display: flex;
    gap: 8px;
  }

  .add-confirm-btn {
    background: #312e81;
    color: #a5b4fc;
    border: 1px solid #6366f1;
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 12px;
    cursor: pointer;
  }
  .add-confirm-btn:hover { background: #3730a3; }

  .add-cancel-btn {
    background: transparent;
    color: #64748b;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 5px 10px;
    font-size: 12px;
    cursor: pointer;
  }
  .add-cancel-btn:hover { color: #94a3b8; }

  /* ── grid columns: icon | label | connectivity | figures | include | chevron ── */
  .grid-header,
  .row-header {
    display: grid;
    grid-template-columns: 26px 1fr 1.4fr 1.6fr 52px 20px;
    align-items: center;
    gap: 0;
  }

  .grid-header {
    padding: 4px 14px;
    border-bottom: 1px solid #1e293b;
    flex-shrink: 0;
  }
  .grid-header > span {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: #475569;
    padding: 0 6px;
  }

  /* ── flat list ── */
  .list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 14px;
  }

  .row {
    background: #1e293b;
    border: 1px solid #263347;
    border-radius: 5px;
    overflow: hidden;
  }
  .row.expanded { border-color: #6366f1; }

  .row-header {
    padding: 5px 6px;
    cursor: pointer;
    user-select: none;
  }
  .row-header:hover { background: #243044; }

  .kind-icon {
    font-size: 14px;
    text-align: center;
    flex-shrink: 0;
    padding: 0 2px;
  }

  .kind-room         { color: #a5b4fc; }
  .kind-opaque       { color: #93c5fd; }
  .kind-glazing      { color: #86efac; }
  .kind-air_exchange { color: #fcd34d; }
  .kind-outdoor      { color: #7dd3fc; }

  .row-id {
    font-size: 12px;
    font-family: monospace;
    font-weight: 600;
    color: #e2e8f0;
    padding: 0 8px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row-conn {
    font-size: 11px;
    color: #64748b;
    font-family: monospace;
    padding: 0 8px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row-figures {
    font-size: 11px;
    color: #94a3b8;
    font-family: monospace;
    padding: 0 8px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .col-include {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 4px;
  }

  .col-include input[type="checkbox"] {
    width: 14px;
    height: 14px;
    cursor: pointer;
    accent-color: #6366f1;
    border: none;
    padding: 0;
    background: unset;
  }

  .row-chevron {
    font-size: 10px;
    color: #475569;
    text-align: right;
    padding-right: 4px;
  }

  .row-editor {
    border-top: 1px solid #334155;
    padding: 12px;
    background: #0f172a;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .editor-footer {
    border-top: 1px solid #1e293b;
    padding-top: 8px;
    margin-top: 2px;
  }

  .delete-btn {
    background: transparent;
    color: #64748b;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
    cursor: pointer;
  }
  .delete-btn:hover { color: #ef4444; border-color: #ef4444; }

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
</style>
