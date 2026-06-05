<script>
	import { SvelteFlow, Background, Controls, MiniMap } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';

	import MassNode from '$lib/nodes/MassNode.svelte';
	import BoundaryNode from '$lib/nodes/BoundaryNode.svelte';
	import SourceNode from '$lib/nodes/SourceNode.svelte';
	import { modelToFlow } from '$lib/modelToFlow.js';
	import { MODELS } from '$lib/models.js';

	const nodeTypes = {
		mass: MassNode,
		boundary: BoundaryNode,
		source: SourceNode
	};

	let selectedId = $state(MODELS[0].id);

	const selected = $derived(MODELS.find((m) => m.id === selectedId));
	const flow = $derived(modelToFlow(selected.model));
</script>

<div class="shell">
	<header>
		<select bind:value={selectedId}>
			{#each MODELS as m}
				<option value={m.id}>{m.label}</option>
			{/each}
		</select>
		<span class="meta">{selected.model.id} · schema {selected.model.schema_version}</span>
		{#if selected.model.notes}
			<span class="notes">{selected.model.notes}</span>
		{/if}
	</header>

	<div class="canvas">
		{#key selectedId}
			<SvelteFlow nodes={flow.nodes} edges={flow.edges} {nodeTypes} fitView>
				<Background />
				<Controls />
				<MiniMap />
			</SvelteFlow>
		{/key}
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

	select {
		background: #334155;
		color: #f1f5f9;
		border: 1px solid #475569;
		border-radius: 4px;
		padding: 4px 8px;
		font-size: 14px;
		font-weight: 600;
		cursor: pointer;
	}

	.meta {
		font-size: 12px;
		opacity: 0.5;
	}

	.notes {
		font-size: 11px;
		opacity: 0.4;
		font-style: italic;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		max-width: 600px;
	}

	.canvas {
		flex: 1;
	}
</style>
