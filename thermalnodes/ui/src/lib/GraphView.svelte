<script>
	import dagre from 'dagre';

	/** @type {{ model: object, selected: {kind:string,id:string}|null, onselect: function }} */
	let { model, selected, onselect } = $props();

	const NODE_W = 140;
	const NODE_H = 44;
	const MARGIN = 40;

	// ── layout ───────────────────────────────────────────────────────────────
	const layout = $derived.by(() => {
		const g = new dagre.graphlib.Graph();
		g.setGraph({ rankdir: 'LR', nodesep: 60, ranksep: 100 });
		g.setDefaultEdgeLabel(() => ({}));

		const allNodes = [
			...(model.masses ?? []).map((n) => ({ ...n, _kind: 'mass' })),
			...(model.boundaries ?? []).map((n) => ({ ...n, _kind: 'boundary' })),
			...(model.sources ?? []).map((n) => ({ ...n, _kind: 'source', id: `_src_${n.id}` }))
		];

		for (const n of allNodes) {
			g.setNode(n.id, { width: NODE_W, height: NODE_H });
		}

		for (const r of model.resistances ?? []) {
			g.setEdge(r.from, r.to, { id: r.id });
		}
		for (const s of model.sources ?? []) {
			g.setEdge(`_src_${s.id}`, s.node, { id: `_srce_${s.id}` });
		}

		dagre.layout(g);

		const positions = {};
		for (const id of g.nodes()) {
			positions[id] = g.node(id);
		}

		// compute SVG viewBox from node positions
		let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
		for (const p of Object.values(positions)) {
			minX = Math.min(minX, p.x - NODE_W / 2);
			minY = Math.min(minY, p.y - NODE_H / 2);
			maxX = Math.max(maxX, p.x + NODE_W / 2);
			maxY = Math.max(maxY, p.y + NODE_H / 2);
		}
		const vbX = minX - MARGIN;
		const vbY = minY - MARGIN;
		const vbW = maxX - minX + MARGIN * 2;
		const vbH = maxY - minY + MARGIN * 2;

		return { positions, allNodes, viewBox: `${vbX} ${vbY} ${vbW} ${vbH}` };
	});

	// ── edge path helper ─────────────────────────────────────────────────────
	function edgePath(fromId, toId) {
		const f = layout.positions[fromId];
		const t = layout.positions[toId];
		if (!f || !t) return '';
		const mx = (f.x + t.x) / 2;
		return `M ${f.x} ${f.y} C ${mx} ${f.y}, ${mx} ${t.y}, ${t.x} ${t.y}`;
	}

	function edgeMid(fromId, toId) {
		const f = layout.positions[fromId];
		const t = layout.positions[toId];
		if (!f || !t) return { x: 0, y: 0 };
		return { x: (f.x + t.x) / 2, y: (f.y + t.y) / 2 };
	}

	// ── resistance label ─────────────────────────────────────────────────────
	function rLabel(r) {
		return `R=${r.R} K/W`;
	}

	// ── select helpers ───────────────────────────────────────────────────────
	function isSelected(kind, id) {
		return selected?.kind === kind && selected?.id === id;
	}

	function sel(kind, id) {
		onselect(isSelected(kind, id) ? null : { kind, id });
	}
</script>

<svg
	class="graph"
	viewBox={layout.viewBox}
	xmlns="http://www.w3.org/2000/svg"
>
	<defs>
		<marker id="arrow-r" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
			<path d="M0,0 L0,6 L8,3 z" fill="#6366f1" />
		</marker>
		<marker id="arrow-s" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
			<path d="M0,0 L0,6 L8,3 z" fill="#f59e0b" />
		</marker>
		<marker id="arrow-r-sel" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
			<path d="M0,0 L0,6 L8,3 z" fill="#818cf8" />
		</marker>
	</defs>

	<!-- resistance edges -->
	{#each model.resistances ?? [] as r}
		{@const mid = edgeMid(r.from, r.to)}
		{@const sel_r = isSelected('resistance', r.id)}
		<path
			d={edgePath(r.from, r.to)}
			fill="none"
			stroke={sel_r ? '#818cf8' : '#6366f1'}
			stroke-width={sel_r ? 3 : 2}
			marker-end={sel_r ? 'url(#arrow-r-sel)' : 'url(#arrow-r)'}
		/>
		<!-- clickable hit area -->
		<path
			d={edgePath(r.from, r.to)}
			fill="none"
			stroke="transparent"
			stroke-width="14"
			style="cursor:pointer"
			onclick={() => sel('resistance', r.id)}
			role="button"
			tabindex="0"
			aria-label={r.label ?? r.id}
			onkeydown={(e) => e.key === 'Enter' && sel('resistance', r.id)}
		/>
		<text
			x={mid.x}
			y={mid.y - 8}
			text-anchor="middle"
			class="edge-label"
			fill={sel_r ? '#818cf8' : '#94a3b8'}
		>{r.label ?? rLabel(r)}</text>
	{/each}

	<!-- source edges (animated via stroke-dasharray trick) -->
	{#each model.sources ?? [] as s}
		{@const fromId = `_src_${s.id}`}
		<path
			d={edgePath(fromId, s.node)}
			fill="none"
			stroke="#f59e0b"
			stroke-width="2"
			stroke-dasharray="6 3"
			marker-end="url(#arrow-s)"
		/>
	{/each}

	<!-- nodes -->
	{#each layout.allNodes as n}
		{@const p = layout.positions[n.id]}
		{@const x = p?.x - NODE_W / 2}
		{@const y = p?.y - NODE_H / 2}
		{@const selNode = isSelected(n._kind === 'source' ? 'source' : n._kind, n._kind === 'source' ? n.id.slice(5) : n.id)}

		<g
			transform={`translate(${x},${y})`}
			style="cursor:pointer"
			onclick={() => sel(n._kind === 'source' ? 'source' : n._kind, n._kind === 'source' ? n.id.slice(5) : n.id)}
			role="button"
			tabindex="0"
			aria-label={n.label ?? n.id}
			onkeydown={(e) => e.key === 'Enter' && sel(n._kind === 'source' ? 'source' : n._kind, n._kind === 'source' ? n.id.slice(5) : n.id)}
		>
			{#if n._kind === 'mass'}
				<rect
					width={NODE_W} height={NODE_H} rx="8"
					fill={selNode ? '#312e81' : '#1e1b4b'}
					stroke={selNode ? '#818cf8' : '#6366f1'}
					stroke-width={selNode ? 2.5 : 1.5}
				/>
				<text x={NODE_W/2} y={NODE_H/2 - 4} text-anchor="middle" class="node-label" fill="#e0e7ff">{n.label ?? n.id}</text>
				<text x={NODE_W/2} y={NODE_H/2 + 10} text-anchor="middle" class="node-sub" fill="#818cf8">
					{`C = ${n.C.toExponential(1)} J/K`}
				</text>

			{:else if n._kind === 'boundary'}
				<rect
					width={NODE_W} height={NODE_H} rx="4"
					fill={selNode ? '#1c1917' : '#0c0a09'}
					stroke={selNode ? '#a3e635' : '#65a30d'}
					stroke-width={selNode ? 2.5 : 1.5}
					stroke-dasharray="6 3"
				/>
				<text x={NODE_W/2} y={NODE_H/2 - 4} text-anchor="middle" class="node-label" fill="#d9f99d">{n.label ?? n.id}</text>
				<text x={NODE_W/2} y={NODE_H/2 + 10} text-anchor="middle" class="node-sub" fill="#84cc16">
					{typeof n.T_source === 'number' ? `${n.T_source} °C` : n.T_source}
				</text>

			{:else if n._kind === 'source'}
				<rect
					width={NODE_W} height={NODE_H} rx="22"
					fill={selNode ? '#451a03' : '#27130a'}
					stroke={selNode ? '#fbbf24' : '#f59e0b'}
					stroke-width={selNode ? 2.5 : 1.5}
				/>
				<text x={NODE_W/2} y={NODE_H/2 - 4} text-anchor="middle" class="node-label" fill="#fef3c7">{n.label ?? n.id}</text>
				<text x={NODE_W/2} y={NODE_H/2 + 10} text-anchor="middle" class="node-sub" fill="#fbbf24">
					×{n.gain}
				</text>
			{/if}
		</g>
	{/each}
</svg>

<style>
	.graph {
		width: 100%;
		height: 100%;
		display: block;
		background: #0f172a;
	}

	.node-label {
		font-size: 12px;
		font-weight: 600;
		font-family: sans-serif;
		pointer-events: none;
	}

	.node-sub {
		font-size: 10px;
		font-family: monospace;
		pointer-events: none;
	}

	.edge-label {
		font-size: 10px;
		font-family: monospace;
		pointer-events: none;
	}
</style>
