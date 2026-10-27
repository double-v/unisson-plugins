<template>
  <!-- Le détail d'une carte `safeplace.signaler` (#931) : le cadre, le libellé
       et le bouton du tampon sont ceux du cœur ; ceci se glisse entre les deux. -->
  <dl
    v-if="action.action_type === 'safeplace.signaler'"
    data-test="safeplace-carte"
    style="display: grid; grid-template-columns: auto 1fr; gap: var(--space-1) var(--space-3); font-size: 0.875rem; margin: 0"
  >
    <dt style="color: var(--color-ink-faint)">Artiste</dt>
    <dd style="margin: 0">
      {{ artiste?.folder_name ?? `#${action.targets?.[0]}` }}
      <span v-if="artiste?.folder_path" style="color: var(--color-ink-faint)">(dossier : {{ artiste.folder_path }})</span>
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
const artiste = ref(null);

onMounted(async () => {
  const id = props.action.targets?.[0];
  if (id == null) return;
  // Le nom et le dossier, pour qu'on sache qui on signale ; l'id seul sinon.
  artiste.value = await api.get(`/artists/${id}`).catch(() => null);
});
</script>
