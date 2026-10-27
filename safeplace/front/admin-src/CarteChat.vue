<template>
  <!-- Le détail d'une carte `safeplace.signaler` (#931) : le cadre, le libellé
       et le bouton du tampon sont ceux du cœur ; ceci se glisse entre les deux. -->
  <dl
    v-if="action.action_type === 'safeplace.signaler'"
    data-test="safeplace-carte"
    style="display: grid; grid-template-columns: auto 1fr; gap: var(--space-1) var(--space-3); font-size: 0.875rem; margin: 0"
  >
    <dt style="color: var(--color-ink-faint)">{{ artistes.length > 1 ? "Artistes" : "Artiste" }}</dt>
    <dd style="margin: 0">
      <!-- Toutes les cibles : chacune devient un signalement au tampon. -->
      <div v-for="a in artistes" :key="a.id">
        {{ a.folder_name ?? `#${a.id}` }}
        <span v-if="a.folder_path" style="color: var(--color-ink-faint)">(dossier : {{ a.folder_path }})</span>
      </div>
    </dd>
    <dt style="color: var(--color-ink-faint)">Motif</dt>
    <dd style="margin: 0">{{ action.params?.reasons || "—" }}</dd>
    <dt style="color: var(--color-ink-faint)">Sévérité</dt>
    <dd style="margin: 0">{{ GRAVITES[action.params?.severity] || action.params?.severity || GRAVITES.autre }}</dd>
    <template v-if="action.params?.source_url">
      <dt style="color: var(--color-ink-faint)">Source</dt>
      <dd style="margin: 0; overflow-wrap: anywhere">
        <a :href="action.params.source_url" target="_blank" rel="noopener" style="text-decoration: underline">{{ action.params.source_url }} ↗</a>
      </dd>
    </template>
    <dt style="color: var(--color-ink-faint)">Ensuite</dt>
    <dd style="margin: 0; color: var(--color-ink-muted)">
      signalement confirmé ; la mise à la corbeille reste un geste séparé, depuis la page Safeplace
    </dd>
  </dl>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { GRAVITES } from "./donnees.js";

const props = defineProps({ action: { type: Object, required: true } });
const { api } = globalThis.__unisson__;
const artistes = ref((props.action.targets ?? []).map((id) => ({ id })));

onMounted(async () => {
  // Le nom et le dossier, pour qu'on sache qui on signale ; l'id seul sinon.
  artistes.value = await Promise.all(
    artistes.value.map(({ id }) => api.get(`/artists/${id}`).then((a) => ({ ...a, id })).catch(() => ({ id }))),
  );
});
</script>
