<script>
  /**
   * Props:
   *   house: the house model object (reactive, bound from parent)
   *   onchange: (newHouse) => void
   *   customMaterials: user-defined materials from MaterialsPanel
   */
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

  // ── derived helpers ───────────────────────────────────────────────────────
  const rooms    = $derived(house?.rooms    ?? []);
  const elements = $derived(house?.elements ?? []);
  const materials = $derived({ ...BUILTIN_MATERIALS, ...(customMaterials ?? {}), ...(house?.materials ?? {}) });

  // ── selected room ─────────────────────────────────────────────────────────
  let selectedRoomId = $state(null);
  const selectedRoom = $derived(rooms.find(r => r.id === selectedRoomId) ?? null);

  // elements for the selected room
  const roomElements = $derived(
    selectedRoomId
      ? elements.filter(el => el.between?.includes(selectedRoomId))
      : []
  );

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

  function deleteElement(id) {
    patchHouse({ elements: elements.filter(el => el.id !== id) });
  }

  function deleteRoom(id) {
    patchHouse({
      rooms:    rooms.filter(r => r.id !== id),
      elements: elements.filter(el => !el.between?.includes(id)),
    });
    if (selectedRoomId === id) selectedRoomId = null;
  }

  // ── add room ──────────────────────────────────────────────────────────────
  let addRoomId    = $state('');
  let addRoomError = $state('');

  function addRoom() {
    const id = addRoomId.trim();
    if (!id) { addRoomError = 'ID required'; return; }
    if (rooms.some(r => r.id === id)) { addRoomError = 'ID already used'; return; }
    patchHouse({ rooms: [...rooms, { id, a: 4, b: 4, c: 2.5 }] });
    addRoomId    = '';
    addRoomError = '';
    selectedRoomId = id;
  }

  // ── add element form ──────────────────────────────────────────────────────
  let newKind = $state('opaque');

  // opaque
  let newOpaqueId    = $state('');
  let newOpaqueA     = $state(4.0);
  let newOpaqueB     = $state(2.5);
  let newOpaqueZoneB = $state('outdoor');
  let newOpaqueOri   = $state('S');
  let newOpaqueTilt  = $state(90);
  let newOpaqueMat   = $state('brick_full');
  let newOpaqueThick = $state(0.2);
  let newOpaqueError = $state('');

  // glazing
  let newGlazId    = $state('');
  let newGlazA     = $state(1.2);
  let newGlazB     = $state(1.4);
  let newGlazZoneB = $state('outdoor');
  let newGlazOri   = $state('S');
  let newGlazU     = $state(2.8);
  let newGlazSHGC  = $state(0.67);
  let newGlazError = $state('');

  // air_exchange
  let newAirId    = $state('');
  let newAirZoneB = $state('outdoor');
  let newAirAch   = $state(0.4);
  let newAirError = $state('');

  function addElement() {
    if (!selectedRoomId) return;

    if (newKind === 'opaque') {
      const id = newOpaqueId.trim() || `wall_${elements.length + 1}`;
      if (elements.some(e => e.id === id)) { newOpaqueError = 'ID already used'; return; }
      patchHouse({ elements: [...elements, {
        id, kind: 'opaque',
        between: [selectedRoomId, newOpaqueZoneB],
        a: newOpaqueA, b: newOpaqueB,
        orientation: newOpaqueOri,
        tilt: newOpaqueTilt,
        layers: [{ material: newOpaqueMat, thickness: newOpaqueThick }],
      }] });
      newOpaqueId = '';
      newOpaqueError = '';

    } else if (newKind === 'glazing') {
      const id = newGlazId.trim() || `win_${elements.length + 1}`;
      if (elements.some(e => e.id === id)) { newGlazError = 'ID already used'; return; }
      patchHouse({ elements: [...elements, {
        id, kind: 'glazing',
        between: [selectedRoomId, newGlazZoneB],
        a: newGlazA, b: newGlazB,
        orientation: newGlazOri,
        tilt: 90,
        U: newGlazU,
        SHGC: newGlazSHGC,
      }] });
      newGlazId = '';
      newGlazError = '';

    } else if (newKind === 'air_exchange') {
      const id = newAirId.trim() || `air_${elements.length + 1}`;
      if (elements.some(e => e.id === id)) { newAirError = 'ID already used'; return; }
      patchHouse({ elements: [...elements, {
        id, kind: 'air_exchange',
        between: [selectedRoomId, newAirZoneB],
        ach: newAirAch,
      }] });
      newAirId = '';
      newAirError = '';
    }
  }

  // ── zone options for "between" dropdown ───────────────────────────────────
  const otherZones = $derived([
    'outdoor', 'ground',
    ...rooms.filter(r => r.id !== selectedRoomId).map(r => r.id),
  ]);

  // ── layer editing ─────────────────────────────────────────────────────────
  function patchLayer(elId, layerIdx, patch) {
    patchHouse({ elements: elements.map(el => {
      if (el.id !== elId) return el;
      const layers = el.layers.map((l, i) => i === layerIdx ? { ...l, ...patch } : l);
      return { ...el, layers };
    })});
  }

  function addLayer(elId) {
    patchHouse({ elements: elements.map(el => {
      if (el.id !== elId) return el;
      return { ...el, layers: [...el.layers, { material: 'plaster', thickness: 0.01 }] };
    })});
  }

  function deleteLayer(elId, layerIdx) {
    patchHouse({ elements: elements.map(el => {
      if (el.id !== elId) return el;
      return { ...el, layers: el.layers.filter((_, i) => i !== layerIdx) };
    })});
  }

  // ── expanded element (for inline editing) ─────────────────────────────────
  let expandedElId = $state(null);
</script>

<div class="house-panel">

  <!-- ── left: rooms list ──────────────────────────────────────────────────── -->
  <aside class="rooms-sidebar">
    <div class="sidebar-title">Rooms</div>

    <div class="rooms-list">
      {#each rooms as room}
        <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
        <div
          class="room-row"
          class:selected={room.id === selectedRoomId}
          onclick={() => selectedRoomId = room.id}
        >
          <span class="room-id">{room.id}</span>
          <span class="room-vol">{((room.a ?? 0) * (room.b ?? 0) * (room.c ?? 0)).toFixed(0)} m³</span>
          <button class="icon-btn del-room" onclick={(e) => { e.stopPropagation(); deleteRoom(room.id); }} title="Delete room">×</button>
        </div>
      {/each}

      {#if rooms.length === 0}
        <div class="empty-hint">No rooms yet</div>
      {/if}
    </div>

    <!-- add room form -->
    <div class="add-room-form">
      <div class="form-title">Add room</div>
      <label class="field">
        <span>id</span>
        <input type="text" bind:value={addRoomId} placeholder="chambre" />
      </label>
      {#if addRoomError}<div class="field-error">{addRoomError}</div>{/if}
      <button class="add-btn" onclick={addRoom}>Add</button>
    </div>
  </aside>

  <!-- ── right: elements for selected room ────────────────────────────────── -->
  <div class="elements-area">
    {#if !selectedRoomId}
      <div class="no-selection">Select a room to see its elements</div>

    {:else}
      <!-- room header + editable fields -->
      <div class="room-header">
        <span class="room-header-id">{selectedRoomId}</span>
        <label class="inline-field">
          <span>a (m)</span>
          <input type="number" value={selectedRoom?.a ?? ''} min="0.1" step="0.5"
            oninput={(e) => patchRoom(selectedRoomId, { a: parseFloat(e.target.value) || 0 })} />
        </label>
        <label class="inline-field">
          <span>b (m)</span>
          <input type="number" value={selectedRoom?.b ?? ''} min="0.1" step="0.5"
            oninput={(e) => patchRoom(selectedRoomId, { b: parseFloat(e.target.value) || 0 })} />
        </label>
        <label class="inline-field">
          <span>c (m)</span>
          <input type="number" value={selectedRoom?.c ?? ''} min="0.1" step="0.1"
            oninput={(e) => patchRoom(selectedRoomId, { c: parseFloat(e.target.value) || 0 })} />
        </label>
        <span class="room-vol-display">= {((selectedRoom?.a ?? 0) * (selectedRoom?.b ?? 0) * (selectedRoom?.c ?? 0)).toFixed(1)} m³</span>
        <label class="inline-field">
          <span>furniture factor</span>
          <input type="number" value={selectedRoom?.furniture_factor ?? 2.5} min="1" step="0.5"
            oninput={(e) => patchRoom(selectedRoomId, { furniture_factor: parseFloat(e.target.value) || 1 })} />
        </label>
      </div>

      <!-- elements list -->
      <div class="elements-list">
        {#each roomElements as el}
          <div class="el-card" class:expanded={expandedElId === el.id}>

            <!-- card header -->
            <div class="el-header">
              <span class="kind-badge kind-{el.kind}">{el.kind}</span>
              <span class="el-id">{el.id}</span>
              <span class="el-between">→ {el.between?.[1]}</span>
              <button class="icon-btn" onclick={() => expandedElId = expandedElId === el.id ? null : el.id}
                title="Edit">{expandedElId === el.id ? '▲' : '▼'}</button>
              <button class="icon-btn del-el" onclick={() => deleteElement(el.id)} title="Delete">×</button>
            </div>

            <!-- summary line -->
            {#if expandedElId !== el.id}
              <div class="el-summary">
                {#if el.kind === 'opaque'}
                  {el.a} × {el.b} m = {(el.a * el.b).toFixed(1)} m² · {el.orientation ?? '—'} · {el.layers?.length ?? 0} layer(s)
                {:else if el.kind === 'glazing'}
                  {el.a} × {el.b} m = {(el.a * el.b).toFixed(2)} m² · U={el.U} · SHGC={el.SHGC}
                {:else if el.kind === 'air_exchange'}
                  {el.ach} ACH
                {/if}
              </div>
            {/if}

            <!-- expanded editor -->
            {#if expandedElId === el.id}
              <div class="el-editor">

                {#if el.kind === 'opaque'}
                  <div class="field-row">
                    <label class="field">
                      <span>a (m)</span>
                      <input type="number" value={el.a} min="0.1" step="0.1"
                        oninput={(e) => patchElement(el.id, { a: parseFloat(e.target.value) || 0 })} />
                    </label>
                    <label class="field">
                      <span>b (m)</span>
                      <input type="number" value={el.b} min="0.1" step="0.1"
                        oninput={(e) => patchElement(el.id, { b: parseFloat(e.target.value) || 0 })} />
                    </label>
                    <label class="field area-display">
                      <span>area</span>
                      <span class="computed-val">{((el.a ?? 0) * (el.b ?? 0)).toFixed(2)} m²</span>
                    </label>
                    <label class="field">
                      <span>orientation</span>
                      <select value={el.orientation ?? 'S'}
                        onchange={(e) => patchElement(el.id, { orientation: e.target.value })}>
                        {#each ORIENTATIONS as o}<option value={o}>{o}</option>{/each}
                      </select>
                    </label>
                    <label class="field">
                      <span>tilt (°)</span>
                      <input type="number" value={el.tilt ?? 90} min="0" max="90" step="5"
                        oninput={(e) => patchElement(el.id, { tilt: parseFloat(e.target.value) || 90 })} />
                    </label>
                    <label class="field">
                      <span>connects to</span>
                      <select value={el.between?.[1] ?? 'outdoor'}
                        onchange={(e) => patchElement(el.id, { between: [el.between[0], e.target.value] })}>
                        {#each otherZones as z}<option value={z}>{z}</option>{/each}
                      </select>
                    </label>
                  </div>

                  <!-- layers -->
                  <div class="layers-section">
                    <div class="layers-title">Layers (interior → exterior)</div>
                    {#each el.layers ?? [] as layer, i}
                      <div class="layer-row">
                        <span class="layer-num">{i + 1}</span>
                        <label class="field">
                          <span>material</span>
                          <select value={layer.material}
                            onchange={(e) => patchLayer(el.id, i, { material: e.target.value })}>
                            {#each Object.entries(materials) as [id, m]}
                              <option value={id}>{m.name ?? id}</option>
                            {/each}
                          </select>
                        </label>
                        <label class="field">
                          <span>thickness (m)</span>
                          <input type="number" value={layer.thickness} min="0.001" step="0.01"
                            oninput={(e) => patchLayer(el.id, i, { thickness: parseFloat(e.target.value) || 0.01 })} />
                        </label>
                        <button class="icon-btn del-el" onclick={() => deleteLayer(el.id, i)} title="Remove layer">×</button>
                      </div>
                    {/each}
                    <button class="add-layer-btn" onclick={() => addLayer(el.id)}>+ Layer</button>
                  </div>

                {:else if el.kind === 'glazing'}
                  <div class="field-row">
                    <label class="field">
                      <span>a (m)</span>
                      <input type="number" value={el.a} min="0.1" step="0.1"
                        oninput={(e) => patchElement(el.id, { a: parseFloat(e.target.value) || 0 })} />
                    </label>
                    <label class="field">
                      <span>b (m)</span>
                      <input type="number" value={el.b} min="0.1" step="0.1"
                        oninput={(e) => patchElement(el.id, { b: parseFloat(e.target.value) || 0 })} />
                    </label>
                    <label class="field area-display">
                      <span>area</span>
                      <span class="computed-val">{((el.a ?? 0) * (el.b ?? 0)).toFixed(2)} m²</span>
                    </label>
                    <label class="field">
                      <span>U (W/m²K)</span>
                      <input type="number" value={el.U} min="0.1" step="0.1"
                        oninput={(e) => patchElement(el.id, { U: parseFloat(e.target.value) || 0 })} />
                    </label>
                    <label class="field">
                      <span>SHGC</span>
                      <input type="number" value={el.SHGC} min="0" max="1" step="0.01"
                        oninput={(e) => patchElement(el.id, { SHGC: parseFloat(e.target.value) || 0 })} />
                    </label>
                    <label class="field">
                      <span>orientation</span>
                      <select value={el.orientation ?? 'S'}
                        onchange={(e) => patchElement(el.id, { orientation: e.target.value })}>
                        {#each ORIENTATIONS as o}<option value={o}>{o}</option>{/each}
                      </select>
                    </label>
                    <label class="field">
                      <span>connects to</span>
                      <select value={el.between?.[1] ?? 'outdoor'}
                        onchange={(e) => patchElement(el.id, { between: [el.between[0], e.target.value] })}>
                        {#each otherZones as z}<option value={z}>{z}</option>{/each}
                      </select>
                    </label>
                  </div>

                {:else if el.kind === 'air_exchange'}
                  <div class="field-row">
                    <label class="field">
                      <span>ACH (h⁻¹)</span>
                      <input type="number" value={el.ach} min="0.01" step="0.1"
                        oninput={(e) => patchElement(el.id, { ach: parseFloat(e.target.value) || 0 })} />
                    </label>
                    <label class="field">
                      <span>connects to</span>
                      <select value={el.between?.[1] ?? 'outdoor'}
                        onchange={(e) => patchElement(el.id, { between: [el.between[0], e.target.value] })}>
                        {#each otherZones as z}<option value={z}>{z}</option>{/each}
                      </select>
                    </label>
                  </div>
                {/if}

              </div>
            {/if}
          </div>
        {/each}

        {#if roomElements.length === 0}
          <div class="empty-hint">No elements for this room yet</div>
        {/if}
      </div>

      <!-- add element form -->
      <div class="add-el-form">
        <div class="form-title">Add element to <em>{selectedRoomId}</em></div>

        <div class="kind-tabs">
          {#each ['opaque', 'glazing', 'air_exchange'] as k}
            <button class="kind-tab" class:active={newKind === k} onclick={() => newKind = k}>{k}</button>
          {/each}
        </div>

        {#if newKind === 'opaque'}
          <div class="field-row">
            <label class="field">
              <span>id (optional)</span>
              <input type="text" bind:value={newOpaqueId} placeholder="mur_S" />
            </label>
            <label class="field">
              <span>a (m)</span>
              <input type="number" bind:value={newOpaqueA} min="0.1" step="0.1" />
            </label>
            <label class="field">
              <span>b (m)</span>
              <input type="number" bind:value={newOpaqueB} min="0.1" step="0.1" />
            </label>
            <label class="field area-display">
              <span>area</span>
              <span class="computed-val">{(newOpaqueA * newOpaqueB).toFixed(2)} m²</span>
            </label>
            <label class="field">
              <span>connects to</span>
              <select bind:value={newOpaqueZoneB}>
                {#each otherZones as z}<option value={z}>{z}</option>{/each}
              </select>
            </label>
            <label class="field">
              <span>orientation</span>
              <select bind:value={newOpaqueOri}>
                {#each ORIENTATIONS as o}<option value={o}>{o}</option>{/each}
              </select>
            </label>
            <label class="field">
              <span>tilt (°)</span>
              <input type="number" bind:value={newOpaqueTilt} min="0" max="90" step="5" />
            </label>
            <label class="field">
              <span>material</span>
              <select bind:value={newOpaqueMat}>
                {#each Object.entries(materials) as [id, m]}
                  <option value={id}>{m.name ?? id}</option>
                {/each}
              </select>
            </label>
            <label class="field">
              <span>thickness (m)</span>
              <input type="number" bind:value={newOpaqueThick} min="0.01" step="0.05" />
            </label>
          </div>
          {#if newOpaqueError}<div class="field-error">{newOpaqueError}</div>{/if}

        {:else if newKind === 'glazing'}
          <div class="field-row">
            <label class="field">
              <span>id (optional)</span>
              <input type="text" bind:value={newGlazId} placeholder="win_S" />
            </label>
            <label class="field">
              <span>a (m)</span>
              <input type="number" bind:value={newGlazA} min="0.1" step="0.1" />
            </label>
            <label class="field">
              <span>b (m)</span>
              <input type="number" bind:value={newGlazB} min="0.1" step="0.1" />
            </label>
            <label class="field area-display">
              <span>area</span>
              <span class="computed-val">{(newGlazA * newGlazB).toFixed(2)} m²</span>
            </label>
            <label class="field">
              <span>connects to</span>
              <select bind:value={newGlazZoneB}>
                {#each otherZones as z}<option value={z}>{z}</option>{/each}
              </select>
            </label>
            <label class="field">
              <span>orientation</span>
              <select bind:value={newGlazOri}>
                {#each ORIENTATIONS as o}<option value={o}>{o}</option>{/each}
              </select>
            </label>
            <label class="field">
              <span>U (W/m²K)</span>
              <input type="number" bind:value={newGlazU} min="0.1" step="0.1" />
            </label>
            <label class="field">
              <span>SHGC</span>
              <input type="number" bind:value={newGlazSHGC} min="0" max="1" step="0.01" />
            </label>
          </div>
          {#if newGlazError}<div class="field-error">{newGlazError}</div>{/if}

        {:else if newKind === 'air_exchange'}
          <div class="field-row">
            <label class="field">
              <span>id (optional)</span>
              <input type="text" bind:value={newAirId} placeholder="infil" />
            </label>
            <label class="field">
              <span>connects to</span>
              <select bind:value={newAirZoneB}>
                {#each otherZones as z}<option value={z}>{z}</option>{/each}
              </select>
            </label>
            <label class="field">
              <span>ACH (h⁻¹)</span>
              <input type="number" bind:value={newAirAch} min="0.01" step="0.1" />
            </label>
          </div>
          {#if newAirError}<div class="field-error">{newAirError}</div>{/if}
        {/if}

        <button class="add-btn" onclick={addElement}>Add</button>
      </div>

    {/if}
  </div>
</div>

<style>
  .house-panel {
    display: flex;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  /* ── rooms sidebar ── */
  .rooms-sidebar {
    width: 200px;
    flex-shrink: 0;
    background: #1e293b;
    border-right: 1px solid #334155;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .sidebar-title {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    padding: 14px 14px 8px;
    border-bottom: 1px solid #334155;
    flex-shrink: 0;
  }

  .rooms-list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 0;
  }

  .room-row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    cursor: pointer;
    border-left: 3px solid transparent;
    transition: background 0.1s;
  }
  .room-row:hover    { background: #243447; }
  .room-row.selected { background: #243447; border-left-color: #6366f1; }

  .room-id {
    flex: 1;
    font-size: 12px;
    font-family: monospace;
    color: #e2e8f0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .room-vol {
    font-size: 11px;
    color: #94a3b8;
    flex-shrink: 0;
  }

  .add-room-form {
    border-top: 1px solid #334155;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex-shrink: 0;
  }

  /* ── elements area ── */
  .elements-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
  }

  .no-selection {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #94a3b8;
    font-size: 13px;
  }

  .room-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 20px;
    background: #1e293b;
    border-bottom: 1px solid #334155;
    flex-shrink: 0;
  }

  .room-header-id {
    font-size: 14px;
    font-weight: 700;
    font-family: monospace;
    color: #f1f5f9;
    flex-shrink: 0;
  }

  .inline-field {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .inline-field > span {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #94a3b8;
    white-space: nowrap;
  }
  .inline-field input {
    width: 70px;
  }

  .room-vol-display {
    font-size: 12px;
    font-family: monospace;
    color: #64748b;
    white-space: nowrap;
    padding-top: 14px;
  }

  .elements-list {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px 16px;
  }

  .empty-hint {
    color: #94a3b8;
    font-size: 12px;
    padding: 16px 0;
  }

  /* ── element cards ── */
  .el-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    overflow: hidden;
  }
  .el-card.expanded { border-color: #6366f1; }

  .el-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
  }

  .el-id {
    font-size: 12px;
    font-family: monospace;
    color: #e2e8f0;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .el-between {
    font-size: 11px;
    color: #94a3b8;
    flex-shrink: 0;
  }

  .el-summary {
    font-size: 11px;
    color: #94a3b8;
    padding: 0 12px 8px;
    font-family: monospace;
  }

  .el-editor {
    border-top: 1px solid #334155;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    background: #0f172a;
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
    margin-bottom: 2px;
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

  /* ── add element form ── */
  .add-el-form {
    border-top: 1px solid #334155;
    padding: 12px 16px;
    background: #1e293b;
    flex-shrink: 0;
  }

  .kind-tabs {
    display: flex;
    gap: 4px;
    margin-bottom: 10px;
  }

  .kind-tab {
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 4px;
    background: #0f172a;
    color: #94a3b8;
    border: 1px solid #334155;
    cursor: pointer;
  }
  .kind-tab:hover  { background: #1e293b; color: #e2e8f0; }
  .kind-tab.active { background: #312e81; color: #a5b4fc; border-color: #6366f1; }

  /* ── shared form helpers ── */
  .form-title {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    margin-bottom: 8px;
  }
  .form-title em { color: #a5b4fc; font-style: normal; }

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

  .field-error {
    font-size: 11px;
    color: #f87171;
  }

  .area-display { justify-content: flex-end; }
  .computed-val {
    font-size: 12px;
    font-family: monospace;
    color: #94a3b8;
    padding: 4px 6px;
    background: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 4px;
  }

  .add-btn {
    margin-top: 6px;
    background: #312e81;
    color: #a5b4fc;
    border: 1px solid #6366f1;
    border-radius: 4px;
    padding: 5px 14px;
    font-size: 12px;
    cursor: pointer;
    align-self: flex-start;
  }
  .add-btn:hover { background: #3730a3; }

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
  .icon-btn:hover { background: #334155; color: #f1f5f9; }
  .del-room:hover, .del-el:hover { color: #ef4444; }

  /* kind badges */
  .kind-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 2px 6px;
    border-radius: 3px;
    flex-shrink: 0;
  }
  .kind-opaque       { background: #1e3a5f; color: #93c5fd; }
  .kind-glazing      { background: #14532d; color: #86efac; }
  .kind-air_exchange { background: #451a03; color: #fcd34d; }
</style>
