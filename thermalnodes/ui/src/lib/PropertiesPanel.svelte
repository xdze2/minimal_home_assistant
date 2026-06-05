<script>
	/**
	 * Props:
	 *   selected: { kind: 'mass'|'boundary'|'source'|'resistance', id: string } | null
	 *   model: the full model object (read-only here)
	 *   onpatch: (kind, id, patch) => void
	 *   onadd: (kind) => void
	 *   ondelete: (kind, id) => void
	 */
	let { selected, model, onpatch, onadd, ondelete } = $props();

	const item = $derived.by(() => {
		if (!selected) return null;
		const { kind, id } = selected;
		if (kind === 'mass') return (model.masses ?? []).find((n) => n.id === id) ?? null;
		if (kind === 'boundary') return (model.boundaries ?? []).find((n) => n.id === id) ?? null;
		if (kind === 'source') return (model.sources ?? []).find((n) => n.id === id) ?? null;
		if (kind === 'resistance') return (model.resistances ?? []).find((r) => r.id === id) ?? null;
		return null;
	});

	function commit(field, value) {
		onpatch(selected.kind, selected.id, { [field]: value });
	}

	function commitR(value) {
		const num = parseFloat(value);
		if (!isNaN(num) && num > 0) onpatch(selected.kind, selected.id, { R: num });
	}

	function commitC(value) {
		const num = parseFloat(value);
		if (!isNaN(num) && num > 0) onpatch(selected.kind, selected.id, { C: num });
	}

	function commitTSource(value) {
		const num = parseFloat(value);
		onpatch(selected.kind, selected.id, { T_source: isNaN(num) ? value : num });
	}

</script>

<aside class="panel">
	{#if !selected || !item}
		<p class="hint">Click a node or edge to edit its properties.</p>
	{:else}
		<div class="header">
			<span class="kind-badge kind-{selected.kind}">{selected.kind}</span>
			<button class="del-btn" onclick={() => ondelete(selected.kind, selected.id)}>Delete</button>
		</div>

		<div class="fields">
			<label>
				<span>id</span>
				<input type="text" value={item.id} disabled />
			</label>

			<label>
				<span>label</span>
				<input
					type="text"
					value={item.label ?? ''}
					oninput={(e) => commit('label', e.target.value)}
				/>
			</label>

			{#if selected.kind === 'mass'}
				<label>
					<span>C (J/K)</span>
					<input
						type="number"
						value={item.C}
						min="1"
						oninput={(e) => commitC(e.target.value)}
					/>
				</label>

			{:else if selected.kind === 'boundary'}
				<label>
					<span>T_source</span>
					<input
						type="text"
						value={String(item.T_source ?? '')}
						oninput={(e) => commitTSource(e.target.value)}
						placeholder="signal_name or 12.0"
					/>
				</label>

			{:else if selected.kind === 'source'}
				<label>
					<span>signal</span>
					<input
						type="text"
						value={item.signal ?? ''}
						oninput={(e) => commit('signal', e.target.value)}
					/>
				</label>
				<label>
					<span>gain</span>
					<input
						type="number"
						value={item.gain ?? 1}
						min="0"
						step="0.1"
						oninput={(e) => commit('gain', parseFloat(e.target.value) || 1)}
					/>
				</label>
				<label>
					<span>target mass</span>
					<select value={item.node ?? ''} onchange={(e) => commit('node', e.target.value)}>
						{#each model.masses ?? [] as m}
							<option value={m.id}>{m.label ?? m.id}</option>
						{/each}
					</select>
				</label>

			{:else if selected.kind === 'resistance'}
				<label>
					<span>from</span>
					<select value={item.from ?? ''} onchange={(e) => commit('from', e.target.value)}>
						{#each [...(model.masses ?? []), ...(model.boundaries ?? [])] as n}
							<option value={n.id}>{n.label ?? n.id}</option>
						{/each}
					</select>
				</label>
				<label>
					<span>to</span>
					<select value={item.to ?? ''} onchange={(e) => commit('to', e.target.value)}>
						{#each [...(model.masses ?? []), ...(model.boundaries ?? [])] as n}
							<option value={n.id}>{n.label ?? n.id}</option>
						{/each}
					</select>
				</label>

				<label>
					<span>R (K/W)</span>
					<input
						type="number"
						value={item.R}
						min="0.001"
						step="0.01"
						oninput={(e) => commitR(e.target.value)}
					/>
				</label>
			{/if}
		</div>
	{/if}

	<div class="add-section">
		<p class="section-title">Add</p>
		<button onclick={() => onadd('mass')}>+ Mass</button>
		<button onclick={() => onadd('boundary')}>+ Boundary</button>
		<button onclick={() => onadd('source')}>+ Source</button>
		<button onclick={() => onadd('resistance')}>+ Resistance</button>
	</div>
</aside>

<style>
	.panel {
		width: 220px;
		flex-shrink: 0;
		background: #1e293b;
		color: #cbd5e1;
		display: flex;
		flex-direction: column;
		overflow-y: auto;
		border-left: 1px solid #334155;
	}

	.hint {
		padding: 16px;
		font-size: 12px;
		color: #64748b;
		margin: 0;
		flex: 1;
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 14px 8px;
		border-bottom: 1px solid #334155;
	}

	.kind-badge {
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		padding: 2px 8px;
		border-radius: 4px;
	}
	.kind-mass       { background: #312e81; color: #a5b4fc; }
	.kind-boundary   { background: #14532d; color: #86efac; }
	.kind-source     { background: #451a03; color: #fcd34d; }
	.kind-resistance { background: #1e1b4b; color: #818cf8; }

	.del-btn {
		background: transparent;
		border: 1px solid #ef4444;
		color: #ef4444;
		border-radius: 4px;
		padding: 2px 8px;
		font-size: 11px;
		cursor: pointer;
	}
	.del-btn:hover { background: #7f1d1d; }

	.fields {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 12px 14px;
		flex: 1;
	}

	label {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	label > span {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #64748b;
	}

	input, select {
		background: #0f172a;
		color: #e2e8f0;
		border: 1px solid #334155;
		border-radius: 4px;
		padding: 4px 8px;
		font-size: 12px;
		font-family: monospace;
		width: 100%;
		box-sizing: border-box;
	}
	input:focus, select:focus {
		outline: none;
		border-color: #6366f1;
	}
	input:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}

	.add-section {
		padding: 12px 14px;
		border-top: 1px solid #334155;
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-top: auto;
	}

	.section-title {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #64748b;
		margin: 0 0 2px;
	}

	button {
		background: #334155;
		color: #cbd5e1;
		border: 1px solid #475569;
		border-radius: 4px;
		padding: 5px 10px;
		font-size: 12px;
		cursor: pointer;
		text-align: left;
	}
	button:hover { background: #475569; }
</style>
