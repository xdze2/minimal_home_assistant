<script>
	import { SvelteFlow, Background, Controls, MiniMap } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';

	import RoomNode from '$lib/nodes/RoomNode.svelte';
	import BoundaryNode from '$lib/nodes/BoundaryNode.svelte';
	import HeatSourceNode from '$lib/nodes/HeatSourceNode.svelte';
	import { modelToFlow } from '$lib/modelToFlow.js';

	import model from '@data/examples/chambre_1r1c.json';

	const nodeTypes = {
		room: RoomNode,
		boundary: BoundaryNode,
		heatsource: HeatSourceNode
	};

	const { nodes: initialNodes, edges: initialEdges } = modelToFlow(model);

	let nodes = $state(initialNodes);
	let edges = $state(initialEdges);
</script>

<div class="shell">
	<header>
		<span class="title">{model.name}</span>
		<span class="meta">{model.id} · schema {model.schema_version}</span>
	</header>

	<div class="canvas">
		<SvelteFlow {nodes} {edges} {nodeTypes} fitView>
			<Background />
			<Controls />
			<MiniMap />
		</SvelteFlow>
	</div>
</div>

<style>
	:global(body) {
		margin: 0;
		font-family: sans-serif;
		background: #f8fafc;
	}

	.shell {
		display: flex;
		flex-direction: column;
		height: 100vh;
	}

	header {
		display: flex;
		align-items: baseline;
		gap: 16px;
		padding: 10px 20px;
		background: #1e293b;
		color: #f1f5f9;
		flex-shrink: 0;
	}

	.title {
		font-size: 16px;
		font-weight: 600;
	}

	.meta {
		font-size: 12px;
		opacity: 0.5;
	}

	.canvas {
		flex: 1;
	}
</style>
