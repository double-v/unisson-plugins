<template>
  <Note v-if="!s && annonce && annonce.type === 'arretee'" ton="info" style="margin-bottom: var(--space-6)">
    <span>Séance « {{ annonce.nom }} » arrêtée. L'ampli reste allumé, sur sa source réseau.</span>
    <template #actions><UiButton intent="ghost" size="sm" @click="emit('fermer')">Fermer</UiButton></template>
  </Note>

  <section v-else-if="!s && annonce && annonce.type === 'echec'" aria-label="Séance" :style="cadre('danger')">
    <div :style="anneau('danger')"><Icone nom="alert" taille="1.6em" /></div>
    <div :style="milieu">
      <span :style="eyebrow">Réveil « {{ annonce.nom }} »</span>
      <span :style="titre">{{ echec.titre }}</span>
      <span :style="sous">{{ echec.texte }}</span>
    </div>
    <div :style="finStyle" style="display: flex; gap: var(--space-2); flex-wrap: wrap">
      <UiButton intent="secondary" size="md" :block="etroit" @click="emit('diagnostic')">Voir le diagnostic</UiButton>
      <UiButton intent="ghost" size="md" :block="etroit" @click="emit('fermer')">Fermer</UiButton>
    </div>
  </section>

  <section v-else-if="s && s.etat !== 'lecture'" aria-label="Séance en cours" aria-live="polite" :style="cadre('primary')">
    <div :style="anneau('faint')"><UiSpinner size="md" /></div>
    <div :style="milieu">
      <span :style="eyebrow">{{ genre }} « {{ s.alarme.nom }} » · démarrage</span>
      <span :style="titre">{{ s.etat === "preparation" ? "Préparation de la séance…" : "Allumage de l'ampli…" }}</span>
      <span :style="sous">{{ s.etat === "preparation"
        ? "Vérification du lien, du lecteur et des pistes, avant d'allumer l'ampli."
        : `Sortie de veille, volume à ${db(s.volume_depart)}, puis lecture (3 essais au plus).` }}</span>
    </div>
    <div :style="finStyle">
      <UiButton intent="danger" size="md" :block="etroit" :loading="arret" @click="emit('arreter')">
        <template #leading><Icone nom="stop" /></template>Arrêter
      </UiButton>
    </div>
  </section>

  <section v-else-if="s" aria-label="Séance en cours" aria-live="polite" :style="cadre('primary')">
    <img v-if="s.piste?.pochette && !pochetteKo" :src="s.piste.pochette" alt="" :style="pochette" @error="pochetteKo = true" />
    <div v-else :style="{ ...pochette, background: degrade }" aria-hidden="true" />
    <div :style="milieu">
      <span :style="eyebrow">{{ genre }} « {{ s.alarme.nom }} » · en cours</span>
      <span :style="{ ...titre, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }">{{ s.piste?.titre || "Lecture en cours" }}</span>
      <span :style="{ ...sous, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }">{{ [s.piste?.artiste, s.piste?.album].filter(Boolean).join(" · ") }}</span>
      <div style="display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4); font-size: var(--text-xs); color: var(--color-ink-muted); margin-top: var(--space-1); align-items: center">
        <span style="display: flex; align-items: center; gap: var(--space-2)">
          <span aria-hidden="true" style="width: 96px; height: 4px; border-radius: 2px; background: var(--color-surface-sunken); overflow: hidden">
            <span :style="{ display: 'block', height: '100%', background: 'var(--color-primary)', width: `${pct}%`, transition: 'width .5s linear' }" />
          </span>
          <span v-if="s.montee === 'interrompue'">Volume {{ db(s.volume) }} · <b style="color: var(--color-ink)">montée interrompue</b>, réglé à la main</span>
          <span v-else-if="s.montee === 'en_cours'">Volume <b style="color: var(--color-ink); font-family: var(--font-mono)">{{ db(s.volume) }}</b> → {{ db(s.volume_cible) }}</span>
          <span v-else>Volume {{ db(s.volume ?? s.volume_cible) }}, atteint</span>
        </span>
        <span style="display: inline-flex; align-items: center; gap: var(--space-1)"><Icone nom="clock" /> {{ finTexte }}</span>
      </div>
    </div>
    <div :style="finStyle">
      <UiButton intent="danger" size="md" :block="etroit" :loading="arret" @click="emit('arreter')">
        <template #leading><Icone nom="stop" /></template>Arrêter
      </UiButton>
    </div>
  </section>
</template>

<script setup>
// Le bandeau de la séance : allumage, lecture (piste, volume qui monte, fin
// prévue) avec « Arrêter », puis ce qui en reste (arrêtée, ou l'échec).
import { computed, ref, watch } from "vue";
import { UiButton, UiSpinner } from "@ds/primitives";
import Icone from "./Icone.vue";
import Note from "./Note.vue";
import { etat } from "./etat.js";
import { db, hm, heureDe } from "./outils.js";

const props = defineProps({ annonce: { type: Object, default: null }, etroit: Boolean, arret: Boolean });
const emit = defineEmits(["arreter", "fermer", "diagnostic"]);

const s = computed(() => etat.seance);
const genre = computed(() => (etat.test && s.value && etat.test.id === s.value.alarme.id ? "Test" : "Réveil"));
const pochetteKo = ref(false);
watch(() => s.value?.piste?.id, () => { pochetteKo.value = false; });

const degrade = computed(() => {
  const h = ((s.value?.piste?.id || 7) * 47) % 360;
  return `linear-gradient(135deg, oklch(0.62 0.11 ${h}), oklch(0.32 0.07 ${h + 40}))`;
});

const pct = computed(() => {
  const x = s.value;
  if (!x) return 0;
  if (x.montee !== "en_cours") return 100;
  const plage = x.volume_cible - x.volume_depart;
  if (!plage || x.volume == null) return 0;
  return Math.max(0, Math.min(100, Math.round(((x.volume - x.volume_depart) / plage) * 100)));
});

const finTexte = computed(() => {
  const x = s.value;
  if (x.fin_mode === "duree") return x.fin_prevue ? `fin à ${hm(heureDe(x.fin_prevue).slice(0, 5))}, puis veille` : "fin après la durée prévue, puis veille";
  if (x.fin_mode === "pistes") {
    const total = (x.pistes_jouees || 0) + (x.pistes_restantes || 0);
    return `piste ${Math.max(1, x.pistes_jouees || 0)} sur ${Math.max(1, total)}, puis veille`;
  }
  return "sans limite : jusqu'à ce qu'on arrête";
});

const ECHECS = {
  ampli_injoignable: ["L'ampli n'a pas répondu", "Ni le lien telnet ni le lecteur réseau n'ont répondu. Rien n'a joué."],
  lien_mort: ["Le lien telnet s'est coupé", "La séance s'est arrêtée en route."],
  lecture_impossible: ["L'ampli n'a pas lancé la lecture", "Il s'est allumé, mais n'est pas passé en lecture après trois essais."],
  adresse_reseau_non_reglee: ["L'adresse réseau d'unisson n'est pas réglée", "L'ampli ne saurait pas où chercher la musique : il n'a pas été allumé."],
  aucune_piste: ["Rien à jouer", "Le contexte de l'alarme n'a aucune piste jouable. L'ampli n'a pas été allumé."],
  aucun_format_commun: ["Aucun format lisible", "Aucune piste n'est dans un format que l'ampli lit. L'ampli n'a pas été allumé."],
};
const echec = computed(() => {
  const a = props.annonce;
  const [titre, texte] = ECHECS[a?.code] || ["La séance n'a pas pu jouer", a?.message || a?.code || ""];
  return { titre, texte };
});

// ── le dessin, sur les jetons ────────────────────────────────────────────
const cadre = (ton) => ({
  display: "grid",
  gridTemplateColumns: props.etroit ? "auto 1fr" : "auto 1fr auto",
  gap: "var(--space-4)", alignItems: "center", padding: "var(--space-4)",
  background: "var(--color-surface)", border: `1px solid var(--color-${ton})`,
  borderRadius: "var(--radius-lg)", boxShadow: "var(--shadow-md)", marginBottom: "var(--space-6)",
});
const anneau = (ton) => ({
  width: "72px", height: "72px", borderRadius: "var(--radius-md)", background: "var(--color-surface-sunken)",
  display: "grid", placeItems: "center", color: ton === "danger" ? "var(--color-danger)" : "var(--color-ink-faint)",
});
const pochette = { width: "72px", height: "72px", borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-cover)", objectFit: "cover", flex: "0 0 auto" };
const milieu = { minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--space-1)" };
const eyebrow = { fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--color-ink-muted)" };
const titre = { fontWeight: 600, fontSize: "var(--text-base)" };
const sous = { color: "var(--color-ink-muted)" };
const finStyle = computed(() => (props.etroit ? { gridColumn: "1 / -1" } : {}));
</script>
