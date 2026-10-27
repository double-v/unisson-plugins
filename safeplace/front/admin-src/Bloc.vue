<template>
  <div v-if="item" data-test="safeplace-bloc" style="display: grid; gap: var(--space-1); font-size: 0.875rem">
    <p><strong>Motif :</strong> {{ item.reasons || "—" }}</p>
    <p><strong>Gravité :</strong> {{ GRAVITES[item.severity] || item.severity }}</p>
    <p v-if="item.source_url">
      <strong>Source :</strong>
      <a :href="item.source_url" target="_blank" rel="noopener" style="text-decoration: underline">{{ item.source_url }}</a>
    </p>
    <p style="color: var(--color-ink-faint)">
      {{ PAR[item.flagged_by] || item.flagged_by }}<template v-if="item.pending_review"> · en attente de validation</template>
      · {{ dateCourte(item.flagged_at) }}
    </p>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { GRAVITES, PAR, dateCourte, signalement } from "./donnees.js";

const props = defineProps({ artiste: { type: Object, required: true } });
const item = ref(null);
onMounted(async () => { item.value = await signalement(props.artiste.id); });
</script>
