<script>
	import { Handle, Position } from '@xyflow/svelte';

	/** @type {{ data: { label: string, T_source: string | number } }} */
	let { data } = $props();

	const tDisplay = $derived(
		typeof data.T_source === 'number' ? `T = ${data.T_source} °C (fixe)` : data.T_source
	);
</script>

<Handle type="source" position={Position.Bottom} />

<div class="node">
	<div class="kind">BOUNDARY</div>
	<div class="label">{data.label}</div>
	<div class="detail">{tDisplay}</div>
</div>

<style>
	.node {
		padding: 10px 14px;
		border: 2px solid #16a34a;
		border-radius: 8px;
		background: #bbf7d0;
		min-width: 130px;
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
		word-break: break-all;
	}
</style>
