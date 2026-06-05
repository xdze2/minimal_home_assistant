<script>
	import { Handle, Position } from '@xyflow/svelte';

	/** @type {{ data: { label: string, signal: string, gain: number } }} */
	let { data } = $props();
</script>

<Handle type="source" position={Position.Left} />

<div class="node">
	<div class="kind">SOURCE</div>
	<div class="label">{data.label}</div>
	<div class="detail">signal: {data.signal}</div>
	<div class="detail">gain: {data.gain}</div>
</div>

<style>
	.node {
		padding: 10px 14px;
		border: 2px solid #d97706;
		border-radius: 8px;
		background: #fef3c7;
		min-width: 160px;
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
