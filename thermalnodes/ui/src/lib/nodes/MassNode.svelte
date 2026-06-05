<script>
	import { Handle, Position } from '@xyflow/svelte';

	/** @type {{ data: { label: string, C: any } }} */
	let { data } = $props();

	const cDisplay = $derived(
		typeof data.C === 'number'
			? `C = ${(data.C / 1e6).toFixed(2)} MJ/K`
			: `C ← ${data.C.assembly_id}`
	);
</script>

<Handle type="target" position={Position.Top} />

<div class="node">
	<div class="kind">MASS</div>
	<div class="label">{data.label}</div>
	<div class="detail">{cDisplay}</div>
</div>

<Handle type="source" position={Position.Bottom} />

<style>
	.node {
		padding: 10px 14px;
		border: 2px solid #3b82f6;
		border-radius: 8px;
		background: #bfdbfe;
		min-width: 140px;
		font-family: sans-serif;
	}
	.kind {
		font-size: 9px;
		font-weight: 700;
		letter-spacing: 0.08em;
		opacity: 0.6;
		margin-bottom: 2px;
	}
	.label {
		font-size: 14px;
		font-weight: 600;
	}
	.detail {
		font-size: 11px;
		margin-top: 3px;
		opacity: 0.75;
	}
</style>
