<template>
  <span data-test="convertir-outil">
    <UiButton intent="secondary" size="sm" @click="ouvert = true">Convertir…</UiButton>
    <UiModal v-model="ouvert" title="Convertir en MP3" :subtitle="album.album_name" test-id="convertir-modale">
      <Convertir v-if="ouvert" :album="album" />
    </UiModal>
  </span>
</template>

<script setup>
import { ref } from "vue";
import { UiButton, UiModal } from "@ds/primitives";
import Convertir from "./Convertir.vue";

// Une ligne de la page qualité : le WMA y est déjà signalé. L'aperçu n'est lu
// qu'à l'ouverture — une page de 200 lignes ne lance pas 200 sondes ffprobe.
defineProps({ album: { type: Object, required: true } });
const ouvert = ref(false);
</script>
