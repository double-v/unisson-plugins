<template>
  <RouterLink
    v-if="item && !item.pending_review"
    to="/p/safeplace/"
    data-test="safeplace-badge"
    style="display: inline-flex; align-items: center; gap: var(--space-1); color: var(--color-danger); text-decoration: none; font-size: 0.75rem; font-weight: 600"
  ><span aria-hidden="true">⚑</span> Signalé</RouterLink>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { signalement } from "./donnees.js";

const props = defineProps({ artiste: { type: Object, required: true } });
const item = ref(null);
onMounted(async () => { item.value = await signalement(props.artiste.id); });
</script>
