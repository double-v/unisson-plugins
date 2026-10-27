<template>
  <div data-test="safeplace-signaler" style="display: grid; gap: var(--space-3)">
    <template v-if="item">
      <p style="font-size: 0.875rem">
        Déjà signalé — {{ GRAVITES[item.severity] || item.severity }}<template v-if="item.pending_review">, en attente de validation</template>.
      </p>
      <p v-if="item.reasons" style="font-size: 0.875rem; color: var(--color-ink-muted)">{{ item.reasons }}</p>
      <div style="display: flex; flex-wrap: wrap; gap: var(--space-2)">
        <UiButton v-if="item.pending_review" intent="primary" size="sm" :loading="occupe" @click="confirmer">Confirmer</UiButton>
        <UiButton :intent="aConfirmer ? 'danger' : 'secondary'" size="sm" :loading="occupe" @click="retirer">
          {{ aConfirmer ? "Confirmer le retrait" : "Retirer le signalement" }}
        </UiButton>
      </div>
    </template>
    <template v-else>
      <UiField v-model="form.reasons" label="Motif" placeholder="Accusations, condamnations, sources…" block />
      <UiSelect v-model="form.severity" label="Gravité">
        <option v-for="(libelle, cle) in GRAVITES" :key="cle" :value="cle">{{ libelle }}</option>
      </UiSelect>
      <UiField v-model="form.source_url" label="Lien vers la source" placeholder="https://…" block />
      <div>
        <UiButton intent="primary" size="sm" :loading="occupe" data-test="safeplace-envoyer" @click="poser">Signaler</UiButton>
      </div>
    </template>
    <p v-if="message" role="status" style="font-size: 0.75rem; color: var(--color-ink-muted)">{{ message }}</p>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { UiButton, UiField, UiSelect } from "@ds/primitives";
import { GRAVITES, oublier, signalement } from "./donnees.js";

const props = defineProps({ artiste: { type: Object, required: true } });
const { api } = globalThis.__unisson__;
const item = ref(null);
const form = reactive({ reasons: "", severity: "autre", source_url: "" });
const occupe = ref(false);
const aConfirmer = ref(false);
const message = ref("");

async function relire() {
  oublier(props.artiste.id);
  item.value = await signalement(props.artiste.id);
}

async function geste(fn, fait) {
  occupe.value = true;
  message.value = "";
  try {
    await fn();
    message.value = fait;
    await relire();
  } catch (e) {
    message.value = e?.response?.data?.detail || e?.message || "Le geste a échoué.";
  } finally {
    occupe.value = false;
  }
}

const poser = () => geste(() => api.post("/plugins/safeplace/flags", {
  artist_id: props.artiste.id,
  reasons: form.reasons.trim(),
  severity: form.severity,
  source_url: form.source_url.trim() || null,
}), "Artiste signalé.");

const confirmer = () => geste(() => api.put(`/plugins/safeplace/flags/${props.artiste.id}/confirm`), "Signalement confirmé.");

function retirer() {
  if (!aConfirmer.value) { aConfirmer.value = true; return; }
  aConfirmer.value = false;
  geste(() => api.delete(`/plugins/safeplace/flags/${props.artiste.id}`), "Signalement retiré.");
}

onMounted(async () => { item.value = await signalement(props.artiste.id); });
</script>
