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

		for (const n of model.nodes ?? []) {
			g.setNode(n.id, { width: NODE_W, height: NODE_H });
		}

		for (const e of model.edges ?? []) {
			g.setEdge(e.from, e.to);
		}

		dagre.layout(g);

		const positions = {};
		for (const id of g.nodes()) {
			positions[id] = g.node(id);
		}

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

		return { positions, viewBox: `${vbX} ${vbY} ${vbW} ${vbH}` };
	});

	// ── edge path helper ─────────────────────────────────────────────────────
	function edgePath(fromId, toId) {
		const f = layout.positions[fromId];
		const t = layout.positions[toId];
		if (!f || !t) return '';
		const mx = (f.x + t.x) / 2;
		return `M ${f.x} ${f.y} C ${mx} ${f.y}, ${mx} ${t.y}, ${t.x} ${t.y}`;
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
	<!-- wire edges -->
	{#each model.edges ?? [] as e}
		<path
			d={edgePath(e.from, e.to)}
			fill="none"
			stroke="#334155"
			stroke-width="2"
		/>
	{/each}

	<!-- nodes -->
	{#each model.nodes ?? [] as n}
		{@const p = layout.positions[n.id]}
		{@const x = p?.x - NODE_W / 2}
		{@const y = p?.y - NODE_H / 2}
		{@const selNode = isSelected(n.kind, n.id)}

		<g
			transform={`translate(${x},${y})`}
			style="cursor:pointer"
			onclick={() => sel(n.kind, n.id)}
			role="button"
			tabindex="0"
			aria-label={n.label ?? n.id}
			onkeydown={(e) => e.key === 'Enter' && sel(n.kind, n.id)}
		>
			{#if n.kind === 'mass'}
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

			{:else if n.kind === 'boundary'}
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

			{:else if n.kind === 'resistance'}
				<!-- Zigzag resistor symbol centered in the node box -->
				<rect
					width={NODE_W} height={NODE_H} rx="4"
					fill={selNode ? '#1e1a2e' : '#0f0d1a'}
					stroke={selNode ? '#818cf8' : '#6366f1'}
					stroke-width={selNode ? 2.5 : 1.5}
				/>
				{@const zx = NODE_W / 2}
				{@const zy = NODE_H / 2 - 2}
				{@const zw = 36}
				{@const zh = 8}
				<!-- zigzag: 5 teeth -->
				<polyline
					points={`
						${zx - zw/2},${zy}
						${zx - zw/2 + zw/10},${zy - zh}
						${zx - zw/2 + 3*zw/10},${zy + zh}
						${zx - zw/2 + 5*zw/10},${zy - zh}
						${zx - zw/2 + 7*zw/10},${zy + zh}
						${zx - zw/2 + 9*zw/10},${zy - zh}
						${zx + zw/2},${zy}
					`.trim()}
					fill="none"
					stroke={selNode ? '#818cf8' : '#6366f1'}
					stroke-width="1.5"
					stroke-linejoin="round"
				/>
				<text x={NODE_W/2} y={NODE_H/2 + 14} text-anchor="middle" class="node-sub" fill={selNode ? '#818cf8' : '#6366f1'}>
					{n.label ?? n.id} — {n.R} K/W
				</text>

			{:else if n.kind === 'source'}
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
</style>
