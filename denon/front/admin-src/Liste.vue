<template>
  <UiSkeleton v-if="etat.alarmes === null && !etat.erreurListe" :rows="3" :cols="1" />

  <UiErrorState v-else-if="etat.erreurListe && etat.alarmes === null"
    :message="`Les alarmes n'ont pas pu être chargées : ${etat.erreurListe.message}`" retry-label="Réessayer" @retry="reessayer" />

  <UiEmpty v-else-if="!lignes.length" eyebrow="Réveil" title="Aucune alarme pour l'instant"
    description="Une alarme allume l'ampli à l'heure dite, monte doucement le volume et joue une playlist ou un tirage de la bibliothèque.">
    <template #actions>
      <UiButton intent="primary" size="md" @click="emit('nouvelle')"><template #leading><Icone nom="plus" /></template>Nouvelle alarme</UiButton>
      <UiButton intent="secondary" size="md" @click="emit('diagnostic')">Vérifier l'ampli d'abord</UiButton>
    </template>
  </UiEmpty>

  <template v-else>
    <Note v-if="erreurGeste" ton="danger" role="alert" style="margin-bottom: var(--space-3)">
      <span>{{ erreurGeste }}</span>
      <template #actions><UiButton intent="ghost" size="sm" @click="erreurGeste = ''">Fermer</UiButton></template>
    </Note>
    <div data-test="denon-alarmes" style="display: flex; flex-direction: column; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); overflow: hidden">
      <div v-for="(l, i) in lignes" :key="l.cle" :data-test="l.test ? 'denon-ligne-test' : 'denon-ligne'"
        :style="ligne(l, i)">
        <!-- l'interrupteur, ou la pastille « Test » -->
        <span :style="zone('sw')">
          <UiChip v-if="l.test" tone="accent">Test</UiChip>
          <UiSwitch v-else :model-value="l.a.active" :label="`Alarme « ${l.a.nom} » active`" :disabled="enCours[l.a.id]"
            @update:model-value="basculer(l.a, $event)" />
        </span>

        <!-- l'heure, le nom, les jours -->
        <div :style="zone('heure')">
          <div :style="{ ...heureStyle, color: estInactive(l) ? 'var(--color-ink-faint)' : undefined }">
            {{ l.test ? l.heure.slice(0, 5) : hm(l.a.heure) }}<small v-if="l.test" style="font-size: var(--text-xs)">{{ l.heure.slice(5) }}</small>
          </div>
          <div style="font-weight: 600; font-size: var(--text-sm); margin-top: 2px">{{ l.test ? l.nom : l.a.nom }}</div>
          <span v-if="l.test || l.a.jours === 0" style="font-size: var(--text-xs); color: var(--color-ink-faint)">une seule fois</span>
          <span v-else :aria-label="libJours(l.a.jours)" style="display: inline-flex; gap: 2px; margin-top: var(--space-1)">
            <span v-for="(j, k) in JOURS" :key="k" :style="jour(l.a.jours & (1 << k))">{{ j }}</span>
          </span>
        </div>

        <!-- ce qui se joue -->
        <div :style="{ ...zone('quoi'), display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0, color: estInactive(l) ? 'var(--color-ink-faint)' : undefined }">
          <span style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis">{{ l.quoi[0] }}</span>
          <span style="font-size: var(--text-xs); color: var(--color-ink-faint)">{{ l.quoi[1] }} · {{ db(l.a.volume_depart_db) }} → {{ db(l.a.volume_cible_db) }}
            {{ l.a.montee_s ? `en ${duree(l.a.montee_s)}` : "d'emblée" }} · {{ fin(l.a) }}</span>
        </div>

        <!-- la prochaine occurrence et le dernier résultat -->
        <div :style="etatStyle">
          <template v-if="l.test">
            <template v-if="t.etat === 'en_attente'">
              <UiChip tone="accent" dot>{{ reste ? `part dans ${reste} s` : "échéance passée, on attend…" }}</UiChip>
              <span :style="petit">à <b style="color: var(--color-ink); font-weight: 600; font-family: var(--font-mono)">{{ t.heure }}</b> ({{ etat.fuseau }})</span>
            </template>
            <template v-else-if="t.etat === 'partie'">
              <UiChip tone="success" dot>partie à {{ heureDepart }}</UiChip>
              <span :style="petit">avec {{ virgule((t.retardMs || 0) / 1000) }} s de retard{{ suite ? ` · ${suite}` : "" }}</span>
            </template>
            <template v-else>
              <UiChip tone="danger" dot>pas partie</UiChip>
              <span :style="petit">attendue à {{ t.heure }}, rien à {{ heurePlus10 }}</span>
            </template>
          </template>
          <template v-else>
            <span :style="petit">
              <template v-if="l.a.prochaine">Prochaine : <b style="color: var(--color-ink); font-weight: 600">{{ quand(l.a.prochaine, etat.fuseau) }}</b></template>
              <template v-else>{{ l.a.jours === 0 && l.a.derniere_echeance ? "Passée, désactivée" : "Désactivée" }}</template>
            </span>
            <span :title="AIDE_RESULTAT[l.a.dernier_resultat] || ''" style="display: inline-flex; flex-wrap: wrap; gap: var(--space-1-5); align-items: center">
              <UiChip :tone="resultat(l.a.dernier_resultat).ton" dot>{{ resultat(l.a.dernier_resultat).lib }}</UiChip>
              <span v-if="l.a.derniere_echeance && l.a.dernier_resultat" style="font-size: var(--text-xs); color: var(--color-ink-faint)">{{ quand(l.a.derniere_echeance, etat.fuseau) }}</span>
            </span>
          </template>
        </div>

        <!-- les gestes -->
        <div :style="{ ...zone('act'), display: 'flex', gap: 'var(--space-1)', alignItems: 'center', justifyContent: 'flex-end' }">
          <UiButton v-if="l.test" intent="ghost" size="sm" @click="retirerTest">Retirer</UiButton>
          <template v-else>
            <UiButton intent="secondary" size="sm" :loading="essai === l.a.id" :icon-only="etroit"
              :label="`Essayer « ${l.a.nom} » maintenant`" :aria-label="`Essayer « ${l.a.nom} » maintenant`" @click="essayer(l.a)">
              <template #leading><Icone nom="play" /></template>
              <template v-if="!etroit">Essayer maintenant</template>
            </UiButton>
            <UiButton intent="ghost" size="sm" icon-only :label="`Modifier « ${l.a.nom} »`" @click="emit('modifier', l.a.id)">
              <template #leading><Icone nom="edit" /></template>
            </UiButton>
            <UiButton intent="ghost" size="sm" icon-only :label="`Supprimer « ${l.a.nom} »`" @click="aSupprimer = l.a.id">
              <template #leading><Icone nom="trash" /></template>
            </UiButton>
          </template>
        </div>

        <div v-if="!l.test && aSupprimer === l.a.id" role="alert" style="grid-column: 1 / -1; display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2); padding: var(--space-2-5) var(--space-3); background: var(--color-danger-soft); border-radius: var(--radius-md)">
          <span style="flex: 1; min-width: 12rem">Supprimer l'alarme « {{ l.a.nom }} » ? Elle ne sonnera plus.</span>
          <UiButton intent="ghost" size="sm" @click="aSupprimer = null">Annuler</UiButton>
          <UiButton intent="danger" size="sm" :loading="enCours[l.a.id]" @click="supprimer(l.a)"><template #leading><Icone nom="trash" /></template>Supprimer</UiButton>
        </div>

        <Note v-if="!l.test && retours[l.a.id]" ton="danger" role="alert" style="grid-column: 1 / -1">
          <b>{{ retours[l.a.id].titre }}</b>
          <span>{{ retours[l.a.id].texte }}
            <a v-if="retours[l.a.id].reglage" :href="retours[l.a.id].reglage" style="color: inherit; font-weight: 600">Régler dans Réglages › Réseau</a>
            <a v-else-if="retours[l.a.id].diagnostic" href="#" style="color: inherit; font-weight: 600" @click.prevent="emit('diagnostic')">Voir le diagnostic</a>
          </span>
        </Note>
      </div>
    </div>
    <div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--space-2); margin-top: var(--space-2); font-size: var(--text-xs); color: var(--color-ink-faint)">
      <span>{{ actives }} alarme{{ actives > 1 ? "s" : "" }} active{{ actives > 1 ? "s" : "" }} · heures en {{ etat.fuseau }}</span>
      <span>Si unisson redémarre moins de 10 min après l'heure, l'alarme part en retard ; au-delà, elle est manquée.</span>
    </div>
  </template>
</template>

<script setup>
// La liste des alarmes : l'interrupteur, l'heure et les jours, ce qui se
// joue, la prochaine occurrence et le dernier résultat, et les gestes
// (essayer, modifier, supprimer). La ligne « Test » du testeur de fuseau
// s'y ajoute en tête, et reste 60 s après son résultat.
import { computed, reactive, ref } from "vue";
import { UiButton, UiChip, UiEmpty, UiErrorState, UiSkeleton, UiSwitch } from "@ds/primitives";
import Icone from "./Icone.vue";
import Note from "./Note.vue";
import { reveil } from "./api.js";
import { chargerAlarmes, chargerSeance, etat, quoi, retirerTest, suiteDuTest } from "./etat.js";
import { AIDE_RESULTAT, JOURS, db, duree, fin, hm, libJours, quand, resultat, virgule } from "./outils.js";

const props = defineProps({ etroit: Boolean });
const emit = defineEmits(["nouvelle", "modifier", "diagnostic", "essaye"]);

const aSupprimer = ref(null);
const essai = ref(null);
const enCours = reactive({});
const retours = reactive({});
const erreurGeste = ref("");

const t = computed(() => etat.test);
const lignes = computed(() => {
  const l = [];
  const test = etat.test;
  if (test && !test.retiree) {
    const modele = test.alarme || (etat.alarmes || []).find((a) => !a.test) || {};
    l.push({ cle: `test-${test.id}`, test: true, heure: test.heure, nom: test.nom, a: modele, quoi: quoi(modele) });
  }
  for (const a of etat.alarmes || []) {
    if (a.test) continue;
    l.push({ cle: a.id, test: false, a, quoi: quoi(a) });
  }
  return l;
});
const actives = computed(() => (etat.alarmes || []).filter((a) => a.active && !a.test).length);
const estInactive = (l) => !l.test && !l.a.active;

const reste = computed(() => Math.max(0, Math.ceil((t.value.echeanceMs - etat.maintenant) / 1000)));
const heurePlus10 = computed(() => {
  const [h, m, s] = t.value.heure.split(":").map(Number);
  const tot = (h * 3600 + m * 60 + s + 10) % 86400;
  return [Math.floor(tot / 3600), Math.floor((tot % 3600) / 60), tot % 60].map((n) => String(n).padStart(2, "0")).join(":");
});
const heureDepart = computed(() => t.value.heure);
const suite = computed(() => suiteDuTest(t.value));

async function reessayer() {
  etat.erreurListe = null;
  etat.alarmes = null;
  await chargerAlarmes();
}

async function basculer(a, active) {
  enCours[a.id] = true;
  erreurGeste.value = "";
  try {
    const r = await reveil.modifier(a.id, { active });
    Object.assign(a, r);
  } catch (e) {
    erreurGeste.value = `« ${a.nom} » n'a pas pu être ${active ? "activée" : "désactivée"} : ${e.message}`;
  } finally {
    enCours[a.id] = false;
  }
}

async function supprimer(a) {
  enCours[a.id] = true;
  erreurGeste.value = "";
  try {
    await reveil.supprimer(a.id);
    aSupprimer.value = null;
    await chargerAlarmes();
  } catch (e) {
    erreurGeste.value = `« ${a.nom} » n'a pas pu être supprimée : ${e.message}`;
  } finally {
    enCours[a.id] = false;
  }
}

const RETOURS = {
  ampli_injoignable: (e) => ({ titre: "Rien n'a joué : l'ampli ne répond pas.", texte: `Vérifiez qu'il est branché et que le contrôle réseau reste actif en veille (${e.message}).`, diagnostic: true }),
  adresse_reseau_non_reglee: (e) => ({ titre: "Rien n'a joué : l'ampli ne saurait pas où chercher la musique.", texte: "L'adresse d'unisson sur le réseau n'est pas réglée.", reglage: e.reglage }),
  aucune_piste: (e) => ({ titre: "Rien n'a joué : il n'y a rien à jouer.", texte: `${e.message}.` }),
  aucun_format_commun: (e) => ({ titre: "Rien n'a joué : aucun format lisible par l'ampli.", texte: `${e.message}.`, diagnostic: true }),
};

async function essayer(a) {
  delete retours[a.id];
  essai.value = a.id;
  try {
    await reveil.essayer(a.id);
    await chargerSeance();
    emit("essaye", a);
  } catch (e) {
    const f = RETOURS[e.code];
    retours[a.id] = f ? f(e) : { titre: "Rien n'a joué.", texte: e.message, diagnostic: e.statut === 409 };
    // La séance refusée devient la « dernière » : la page est prévenue avant
    // de la relire, pour ne pas dire l'échec deux fois.
    emit("essaye", a, e);
    await chargerSeance();
  } finally {
    essai.value = null;
    chargerAlarmes();
  }
}

// ── le dessin ────────────────────────────────────────────────────────────
function ligne(l, i) {
  return {
    display: "grid",
    gridTemplateColumns: props.etroit ? "auto minmax(0, 1fr) auto" : "auto 7.5rem minmax(0,1.4fr) minmax(0,1fr) auto",
    gridTemplateAreas: props.etroit ? '"sw heure act" "quoi quoi quoi" "etat etat etat"' : undefined,
    rowGap: props.etroit ? "var(--space-2-5)" : undefined,
    columnGap: "var(--space-4)",
    alignItems: "center",
    padding: "var(--space-4)",
    borderTop: i ? "1px solid var(--color-border)" : undefined,
    background: l.test ? "var(--color-surface-2)" : undefined,
  };
}
function zone(nom) {
  if (!props.etroit) return {};
  const z = { gridArea: nom };
  if (nom === "sw" || nom === "act") Object.assign(z, { alignSelf: "start" });
  if (nom === "sw") z.marginTop = "4px";
  return z;
}
const etatStyle = computed(() => ({
  ...zone("etat"),
  display: "flex",
  flexDirection: props.etroit ? "row" : "column",
  flexWrap: props.etroit ? "wrap" : undefined,
  alignItems: props.etroit ? "center" : "flex-start",
  gap: "var(--space-1-5)",
  minWidth: 0,
}));
const heureStyle = {
  fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", fontSize: "var(--text-xl)",
  fontWeight: 500, letterSpacing: "-0.02em", lineHeight: 1.1,
};
const petit = { fontSize: "var(--text-xs)", color: "var(--color-ink-muted)" };
const jour = (on) => ({
  fontFamily: "var(--font-mono)", fontSize: "10px", width: "15px", height: "15px", display: "grid", placeItems: "center",
  borderRadius: "3px", color: on ? "var(--color-primary-ink)" : "var(--color-ink-faint)",
  background: on ? "var(--color-primary-soft)" : undefined, fontWeight: on ? 600 : undefined,
});

</script>
