<template>
  <div data-test="safeplace-page" style="display: grid; gap: var(--space-4)">
    <header>
      <h2 style="font-size: 1.5rem; font-weight: 700">Safeplace</h2>
      <p style="font-size: 0.875rem; color: var(--color-ink-muted)">
        Les artistes que vous avez signalés, et ceux que l'assistant suggère. Un signalement ne touche à aucun fichier :
        la corbeille passe par le tampon d'opérations.
      </p>
    </header>

    <section v-if="enAttente.length" data-test="safeplace-en-attente"
      style="display: grid; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-warning-soft)">
      <h3 style="font-weight: 600">En attente de validation · {{ enAttente.length }}</h3>
      <div v-for="i in enAttente" :key="i.artist_id" style="display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2)">
        <RouterLink :to="`/library/artists/${i.artist_id}`" style="font-weight: 600">{{ i.artist_name }}</RouterLink>
        <UiChip :tone="TON[i.severity]">{{ GRAVITES[i.severity] }}</UiChip>
        <span style="flex: 1; min-width: 12rem; font-size: 0.75rem; color: var(--color-ink-muted)">{{ i.reasons }}</span>
        <UiButton intent="primary" size="sm" @click="geste(() => api.put(`${BASE}/${i.artist_id}/confirm`), 'Signalement confirmé.')">Confirmer</UiButton>
        <UiButton intent="ghost" size="sm" @click="geste(() => api.delete(`${BASE}/${i.artist_id}`), 'Suggestion rejetée.')">Rejeter</UiButton>
      </div>
    </section>

    <div style="display: flex; flex-wrap: wrap; gap: var(--space-2)">
      <UiSelect v-model="gravite" label="Gravité">
        <option value="">Toutes</option>
        <option v-for="(libelle, cle) in GRAVITES" :key="cle" :value="cle">{{ libelle }}</option>
      </UiSelect>
    </div>

    <p v-if="message" role="status" style="font-size: 0.75rem; color: var(--color-ink-muted)">{{ message }}</p>

    <UiEmpty v-if="charge && !items.length" title="Aucun artiste signalé" description="Signalez un artiste depuis sa fiche, par « Actions »." />

    <ul style="display: grid; gap: var(--space-2)">
      <li v-for="i in items" :key="i.artist_id" data-test="safeplace-ligne"
        style="display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface)">
        <div style="flex: 1; min-width: 14rem; display: grid; gap: var(--space-1)">
          <div style="display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2)">
            <RouterLink :to="`/library/artists/${i.artist_id}`" style="font-weight: 600">{{ i.artist_name }}</RouterLink>
            <UiChip :tone="TON[i.severity]">{{ GRAVITES[i.severity] }}</UiChip>
          </div>
          <span style="font-size: 0.75rem; color: var(--color-ink-muted)">
            {{ i.genre_name || "—" }} · {{ i.album_count }} album(s) · {{ taille(i.total_size_bytes) }}
          </span>
          <span v-if="i.reasons" style="font-size: 0.875rem">{{ i.reasons }}</span>
          <span style="font-size: 0.75rem; color: var(--color-ink-faint)">
            {{ PAR[i.flagged_by] || i.flagged_by }} · {{ dateCourte(i.flagged_at) }}
            <template v-if="i.source_url"> · <a :href="i.source_url" target="_blank" rel="noopener" style="text-decoration: underline">source</a></template>
          </span>
        </div>
        <UiButton intent="danger" size="sm" @click="corbeille(i)">Proposer la corbeille</UiButton>
        <UiButton intent="ghost" size="sm" @click="retirer(i)">{{ aRetirer === i.artist_id ? "Confirmer le retrait" : "Retirer" }}</UiButton>
      </li>
    </ul>

    <div v-if="items.length < total">
      <UiButton intent="secondary" size="sm" @click="charger(false)">Afficher plus</UiButton>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { UiButton, UiChip, UiEmpty, UiSelect } from "@ds/primitives";
import { GRAVITES, PAR, dateCourte, oublier } from "./donnees.js";

const BASE = "/plugins/safeplace/flags";
const TON = { "condamné": "danger", "accusé": "warning", "autre": "neutral" };
const { api } = globalThis.__unisson__;

const items = ref([]);
const total = ref(0);
const enAttente = ref([]);
const gravite = ref("");
const charge = ref(false);
const message = ref("");
const aRetirer = ref(null);

function taille(octets) {
  const go = octets / 1e9;
  return go >= 1 ? `${go.toFixed(1)} Go` : `${Math.round(octets / 1e6)} Mo`;
}

async function charger(depuisLeDebut = true) {
  const params = { pending_review: 0, limit: 100, offset: depuisLeDebut ? 0 : items.value.length };
  if (gravite.value) params.severity = gravite.value;
  const page = await api.get(BASE, params);
  items.value = depuisLeDebut ? page.items : items.value.concat(page.items);
  total.value = page.total;
  enAttente.value = (await api.get(BASE, { pending_review: 1, limit: 200 })).items;
  charge.value = true;
}

async function geste(fn, fait) {
  message.value = "";
  try {
    const r = await fn();
    message.value = typeof fait === "function" ? fait(r) : fait;
    await charger();
  } catch (e) {
    message.value = e?.response?.data?.detail || e?.message || "Le geste a échoué.";
  }
}

function retirer(i) {
  if (aRetirer.value !== i.artist_id) { aRetirer.value = i.artist_id; return; }
  aRetirer.value = null;
  oublier(i.artist_id);
  geste(() => api.delete(`${BASE}/${i.artist_id}`), "Signalement retiré.");
}

// La mise à la corbeille est une opération **du cœur** : le plugin la
// propose au tampon, avec sa provenance ; l'envoi automatique, s'il est
// réglé, l'applique aussitôt.
function corbeille(i) {
  geste(
    () => api.post("/operations/staged", [{ operation_type: "trash_artist", source: "safeplace", target_type: "artist", target_id: i.artist_id }]),
    (rendues) => ([].concat(rendues || []).every((o) => o.status === "pending")
      ? `« ${i.artist_name} » attend au tampon (Opérations).`
      : `« ${i.artist_name} » : opération envoyée.`),
  );
}

watch(gravite, () => charger());
onMounted(() => charger());
</script>
