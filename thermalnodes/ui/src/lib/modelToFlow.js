/**
 * Convert a thermalnodes RC model JSON into Svelteflow nodes + edges.
 *
 * Schema vocabulary (v0.2):
 *   masses      → Svelteflow nodes, type "mass"
 *   boundaries  → Svelteflow nodes, type "boundary"
 *   sources     → Svelteflow nodes, type "source"  + animated edge to target mass
 *   resistances → Svelteflow edges, type "resistance"
 */

/** @param {object} model */
export function modelToFlow(model) {
	/** @type {import('@xyflow/svelte').Node[]} */
	const nodes = [];
	/** @type {import('@xyflow/svelte').Edge[]} */
	const edges = [];

	for (const m of model.masses ?? []) {
		nodes.push({
			id: m.id,
			type: 'mass',
			position: m.ui_position ?? { x: 200, y: 300 },
			data: { label: m.label ?? m.id, C: m.C }
		});
	}

	for (const b of model.boundaries ?? []) {
		nodes.push({
			id: b.id,
			type: 'boundary',
			position: b.ui_position ?? { x: 200, y: 80 },
			data: { label: b.label ?? b.id, T_source: b.T_source }
		});
	}

	for (const s of model.sources ?? []) {
		const sourceNodeId = `_src_${s.id}`;
		const targetMass = (model.masses ?? []).find((m) => m.id === s.node);
		const pos = targetMass?.ui_position
			? { x: targetMass.ui_position.x + 240, y: targetMass.ui_position.y }
			: { x: 440, y: 300 };

		nodes.push({
			id: sourceNodeId,
			type: 'source',
			position: pos,
			data: { label: s.label ?? s.id, signal: s.signal, gain: s.gain }
		});

		edges.push({
			id: `_srce_${s.id}`,
			source: sourceNodeId,
			target: s.node,
			animated: true,
			style: 'stroke: #f59e0b; stroke-width: 2px;',
			markerEnd: { type: 'arrowclosed', color: '#f59e0b' }
		});
	}

	for (const r of model.resistances ?? []) {
		const rLabel =
			typeof r.R === 'number'
				? `R = ${r.R} K/W`
				: `${r.R.construction_id} · ${r.R.area} m²`;
		edges.push({
			id: r.id,
			source: r.from,
			target: r.to,
			label: r.label ? `${r.label} — ${rLabel}` : rLabel,
			style: 'stroke: #6366f1; stroke-width: 2px;',
			markerEnd: { type: 'arrowclosed', color: '#6366f1' }
		});
	}

	return { nodes, edges };
}
