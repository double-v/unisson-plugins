<template>
  <div data-test="convertir-apercu" style="display: grid; gap: var(--space-3)">
    <p v-if="chargement" style="font-size: 0.875rem; color: var(--color-ink-muted)">Lecture de l'album…</p>
    <p v-else-if="erreur" role="alert" style="font-size: 0.875rem">{{ erreur }}</p>
    <template v-else-if="vue">
      <p v-if="!vue.pistes.length" style="font-size: 0.875rem">Cet album n'a aucune piste WMA : rien à convertir.</p>
      <template v-else>
        <p style="font-size: 0.875rem">
          Réencode les WMA en MP3 (CBR, au premier débit au moins égal à la source) et recopie leurs tags en ID3v2.4.
          Les WMA partent à la corbeille ; la conversion se révoque depuis l'historique des opérations.
        </p>
        <table style="width: 100%; font-size: 0.8125rem; border-collapse: collapse">
          <thead>
            <tr style="text-align: left; color: var(--color-ink-muted)">
              <th style="padding: var(--space-1)">Piste</th>
              <th style="padding: var(--space-1)">Devient</th>
              <th style="padding: var(--space-1)">Débit</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in vue.pistes" :key="p.track_id" :data-convertible="p.convertible">
              <td style="padding: var(--space-1); overflow-wrap: anywhere">{{ nomDe(p.source) }}</td>
              <td style="padding: var(--space-1); overflow-wrap: anywhere">
                <template v-if="p.convertible">{{ p.nom_cible }}</template>
                <span v-else style="color: var(--color-ink-muted)">gardée — {{ p.motif_libelle || p.motif }}</span>
              </td>
              <td style="padding: var(--space-1); white-space: nowrap">
                <template v-if="p.convertible">{{ p.debit_source || "?" }} → {{ p.debit_cible }} kbps</template>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="vue.a_convertir" style="font-size: 0.8125rem; color: var(--color-ink-muted)">
          À la corbeille : {{ vue.corbeille.length }} fichier{{ vue.corbeille.length > 1 ? "s" : "" }} WMA.
        </p>
        <p v-if="!vue.ffmpeg" role="alert" style="font-size: 0.8125rem">ffmpeg est introuvable sur le serveur : la conversion ne peut pas tourner.</p>
        <p v-else-if="!vue.mode_edition" role="alert" style="font-size: 0.8125rem">
          Le mode édition est coupé : la conversion peut attendre au tampon, elle ne s'appliquera qu'une fois activé.
        </p>
        <div v-if="vue.a_convertir">
          <UiButton intent="primary" size="sm" :loading="occupe" :disabled="!vue.ffmpeg || !!etat" data-test="convertir-tamponner" @click="tamponner">
            Tamponner la conversion ({{ vue.a_convertir }} piste{{ vue.a_convertir > 1 ? "s" : "" }})
          </UiButton>
        </div>
      </template>
      <p v-if="message" role="status" style="font-size: 0.8125rem; color: var(--color-ink-muted)">{{ message }}</p>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { UiButton } from "@ds/primitives";

// Monté par la carte du hub (`album` : la fiche) et par l'outil de la page
// qualité (`album` : une ligne, `album_id`) : les deux lisent le même aperçu.
const props = defineProps({ album: { type: Object, required: true } });
const { api } = globalThis.__unisson__;
const albumId = computed(() => props.album.album_id ?? props.album.id);
const vue = ref(null);
const chargement = ref(true);
const erreur = ref("");
const occupe = ref(false);
const etat = ref("");
const message = ref("");

const nomDe = (chemin) => chemin.split("/").pop();

function motifErreur(e) {
  return e?.response?.data?.detail || e?.message || "La requête a échoué.";
}

async function tamponner() {
  occupe.value = true;
  message.value = "";
  try {
    const ops = await api.post("/operations/staged", [{
      operation_type: "convertir.mp3",
      source: "convertir",
      target_type: "album",
      target_id: albumId.value,
      params_json: { track_ids: vue.value.pistes.filter((p) => p.convertible).map((p) => p.track_id) },
    }]);
    // L'écran dit ce que le serveur a fait, pas ce qu'on espérait (#1116).
    const op = Array.isArray(ops) ? ops[0] : null;
    etat.value = op?.status || "";
    message.value = op?.status === "pending"
      ? "Au tampon : la conversion attend votre approbation dans « Opérations »."
      : `État rendu : ${op?.status || "inconnu"}${op?.reason ? ` (${op.reason})` : ""}.`;
  } catch (e) {
    message.value = motifErreur(e);
  } finally {
    occupe.value = false;
  }
}

onMounted(async () => {
  try {
    vue.value = await api.get(`/plugins/convertir/albums/${albumId.value}/apercu`);
  } catch (e) {
    erreur.value = motifErreur(e);
  } finally {
    chargement.value = false;
  }
});
</script>
