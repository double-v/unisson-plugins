<template>
  <div ref="racine" data-test="denon-reveil" style="max-width: 960px; min-width: 0; font-size: var(--text-sm); line-height: var(--text-sm-lh)">
    <nav aria-label="Fil d'Ariane" style="display: flex; gap: var(--space-1-5); font-size: var(--text-xs); color: var(--color-ink-faint); margin-bottom: var(--space-2); flex-wrap: wrap">
      <RouterLink to="/plugins" style="color: inherit; text-decoration: none">Extensions</RouterLink><span>›</span>
      <span>Denon</span><span>›</span>
      <span>{{ vue === "nouvelle" ? "Nouvelle alarme" : vue === "modifier" ? "Modifier" : "Réveil" }}</span>
    </nav>

    <Formulaire v-if="vue !== 'liste'" :key="String(route.query.alarme)" :id="vue === 'modifier' ? idEdite : null" :etroit="etroit"
      @retour="revenir" @enregistree="revenir" />

    <template v-else>
      <div style="display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-6)">
        <div>
          <span :style="eyebrow">Denon · {{ etat.diagnostic?.pilote?.libelle?.replace(/^Denon /, "") || "réveil" }}</span>
          <h1 :style="titreH1">Réveil</h1>
          <p style="margin: var(--space-2) 0 0; color: var(--color-ink-muted); max-width: 60ch">
            L'ampli s'allume à l'heure dite, sur une playlist ou un tirage de la bibliothèque, et le volume monte doucement.
          </p>
        </div>
        <span v-if="etat.alarmes?.some((a) => !a.test)" :style="{ display: 'inline-flex', width: etroit ? '100%' : undefined }">
          <UiButton intent="primary" size="md" :block="etroit" @click="nouvelle"><template #leading><Icone nom="plus" /></template>Nouvelle alarme</UiButton>
        </span>
      </div>

      <Seance :annonce="annonce" :etroit="etroit" :arret="arret" :erreur-arret="erreurArret" @arreter="arreter" @fermer="fermerAnnonce"
        @diagnostic="onglet = 'diagnostic'" />

      <div role="tablist" aria-label="Réveil" :style="barre">
        <button v-for="(o, i) in onglets" :key="o.v" type="button" role="tab" :aria-selected="onglet === o.v" :tabindex="onglet === o.v ? 0 : -1"
          :style="tab(onglet === o.v)" @click="onglet = o.v" @keydown="clavierOnglets($event, i)">
          {{ o.lib }}
          <span v-if="o.v === 'alarmes'" :style="compte(onglet === o.v)">{{ nbAlarmes }}</span>
          <span v-if="o.v === 'diagnostic' && aVerifier" aria-label="à vérifier" role="img"
            style="width: 7px; height: 7px; border-radius: 50%; background: var(--color-danger)" />
          <span v-if="onglet === o.v" aria-hidden="true"
            style="position: absolute; left: 0; right: 0; bottom: 0; height: 2px; background: var(--color-primary); border-radius: 2px 2px 0 0" />
        </button>
      </div>
      <div role="tabpanel">
        <Liste v-if="onglet === 'alarmes'" :etroit="etroit" @nouvelle="nouvelle" @modifier="modifier" @diagnostic="onglet = 'diagnostic'" @essaye="essaye" />
        <Diagnostic v-else :etroit="etroit" />
      </div>
    </template>
  </div>
</template>

<script setup>
// La page « Réveil » (Extensions › Denon) : la séance en cours, les onglets
// Alarmes et Diagnostic, et le formulaire d'une alarme sur sa propre page
// (`?alarme=nouvelle` ou `?alarme=<id>`, pour que « précédent » ramène à la
// liste).
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { UiButton } from "@ds/primitives";
import Diagnostic from "./Diagnostic.vue";
import Formulaire from "./Formulaire.vue";
import Icone from "./Icone.vue";
import Liste from "./Liste.vue";
import Seance from "./Seance.vue";
import {
  arreterSeance, arreterSuiviTest, battre, chargerAlarmes, chargerDiagnostic, chargerSeance, etat, reprendreSuiviTest, serveurMaintenant,
} from "./etat.js";
import { fuseauNavigateur, murale } from "./outils.js";

const route = useRoute();
const router = useRouter();

// ── la largeur : sous 760 px, la mise en page du téléphone ───────────────
const racine = ref(null);
const etroit = ref(false);
let observateur = null;

const vue = computed(() => {
  const a = route.query.alarme;
  if (a === "nouvelle") return "nouvelle";
  return a && /^\d+$/.test(String(a)) ? "modifier" : "liste";
});
const idEdite = computed(() => Number(route.query.alarme));
const onglet = ref(route.query.onglet === "diagnostic" ? "diagnostic" : "alarmes");
watch(onglet, (o) => {
  if (o === "diagnostic") chargerDiagnostic();
  router.replace({ query: o === "diagnostic" ? { onglet: o } : {} });
});

function nouvelle() { router.push({ query: { alarme: "nouvelle" } }); window.scrollTo(0, 0); }
function modifier(id) { router.push({ query: { alarme: String(id) } }); window.scrollTo(0, 0); }
function revenir() {
  router.push({ query: {} });
  onglet.value = "alarmes";
}

const onglets = [{ v: "alarmes", lib: "Alarmes" }, { v: "diagnostic", lib: "Diagnostic" }];

// Le clavier des onglets (motif ARIA) : ←/→ passent au voisin (en boucle),
// Début et Fin au premier et au dernier ; la sélection suit le focus. Les
// touches se lisent ici : l'hôte ne prête pas `withKeys` aux plugins.
function clavierOnglets(e, i) {
  const n = onglets.length;
  const cible = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
  if (cible === undefined) return;
  e.preventDefault();
  onglet.value = onglets[cible].v;
  const boutons = e.currentTarget.parentElement?.querySelectorAll('[role="tab"]');
  boutons?.[cible]?.focus();
}
const nbAlarmes = computed(() => (etat.alarmes || []).filter((a) => !a.test).length);
const aVerifier = computed(() => {
  void etat.maintenant;
  const d = etat.diagnostic;
  if (!d && !etat.erreurDiagnostic) return false;
  if (etat.erreurDiagnostic || !d.ok) return true;
  if (etat.decalageServeurMs == null) return false;
  const nav = fuseauNavigateur();
  return Math.abs((murale(serveurMaintenant(), etat.fuseau) - murale(new Date(), nav)) / 1000) > 60;
});

// ── la séance : ce qu'on annonce quand elle finit ────────────────────────
// La dernière séance déjà connue à l'ouverture ne s'annonce pas ; une
// nouvelle, si elle a été arrêtée ou si elle a échoué, oui.
const ECHECS = ["ampli_injoignable", "lien_mort", "lecture_impossible", "adresse_reseau_non_reglee", "aucune_piste", "aucun_format_commun"];
const annonce = ref(null);
const arret = ref(false);
let cleVue = undefined;
const cle = (d) => (d ? `${d.alarme?.id}|${d.debut}|${d.resultat}` : "");

watch(() => etat.derniere, (d) => {
  const k = cle(d);
  // Avant le premier relevé (posé par `onMounted`), rien ne s'annonce.
  if (cleVue === undefined || k === cleVue) return;
  cleVue = k;
  // Le résultat d'un test se lit dans sa ligne et dans la carte « L'heure » ;
  // le refus d'« Essayer », sur la ligne de l'alarme.
  if (!d || (etat.test && d.alarme?.id === etat.test.id)) return;
  if (refusEssai !== null && d.alarme?.id === refusEssai) { refusEssai = null; return; }
  if (d.resultat === "arretee") annonce.value = { type: "arretee", nom: d.alarme.nom };
  else if (ECHECS.includes(d.resultat) || String(d.resultat).startsWith("erreur:")) {
    annonce.value = { type: "echec", nom: d.alarme.nom, code: d.resultat, message: d.message };
  }
});

let refusEssai = null;
function essaye(a, erreur) {
  // Le refus d'« Essayer » se dit sur la ligne : la bannière ne le répète pas.
  if (erreur) {
    refusEssai = a.id;
    return;
  }
  annonce.value = null;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

const erreurArret = ref("");
async function arreter() {
  arret.value = true;
  erreurArret.value = "";
  try {
    await arreterSeance();
  } catch (e) {
    // La séance continue peut-être : le bandeau le dit, et on relit l'état.
    erreurArret.value = `L'arrêt a échoué : ${e.message}`;
    await chargerSeance({ force: true });
  } finally {
    arret.value = false;
  }
}
// Une nouvelle séance (ou plus de séance) efface l'erreur d'un arrêt raté.
watch(() => etat.seance?.debut, () => { erreurArret.value = ""; });
function fermerAnnonce() { annonce.value = null; }

// ── les relevés ──────────────────────────────────────────────────────────
let seconde = null;
let sonde = null;
let tours = 0;
function sonder() {
  // Toutes les 2 s pendant une séance, sinon toutes les 10 s : une alarme
  // de l'ordonnanceur doit apparaître sans recharger la page.
  tours += 1;
  if (etat.seance || tours % 5 === 0) chargerSeance();
  if (tours % 15 === 0 && vue.value === "liste") chargerAlarmes();
}

onMounted(() => {
  if (racine.value && typeof ResizeObserver !== "undefined") {
    observateur = new ResizeObserver(([e]) => { etroit.value = e.contentRect.width < 760; });
    observateur.observe(racine.value);
  }
  chargerAlarmes();
  chargerSeance({ force: true }).then(() => { cleVue = cle(etat.derniere); });
  chargerDiagnostic();
  reprendreSuiviTest();
  seconde = setInterval(battre, 1000);
  sonde = setInterval(sonder, 2000);
});
onBeforeUnmount(() => {
  observateur?.disconnect();
  clearInterval(seconde);
  clearInterval(sonde);
  arreterSuiviTest();
});

// ── le dessin ────────────────────────────────────────────────────────────
const eyebrow = { fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--color-ink-muted)" };
const titreH1 = {
  fontFamily: "var(--font-display)", fontSize: "var(--text-3xl)", lineHeight: "var(--text-3xl-lh)",
  letterSpacing: "var(--text-3xl-ls)", fontWeight: 600, margin: "var(--space-1) 0 0",
};
const barre = { display: "flex", gap: "var(--space-4)", boxShadow: "inset 0 -1px 0 var(--color-border)", marginBottom: "var(--space-6)", overflowX: "auto", scrollbarWidth: "none" };
const tab = (on) => ({
  position: "relative", appearance: "none", background: "transparent", border: 0, padding: "var(--space-2-5) 0", flexShrink: 0,
  font: "inherit", fontSize: "var(--text-sm)", fontWeight: on ? 600 : 500, color: on ? "var(--color-ink)" : "var(--color-ink-muted)",
  cursor: "pointer", display: "inline-flex", alignItems: "center", gap: "var(--space-1-5)", minHeight: "var(--touch-min)",
});
const compte = (on) => ({
  fontFamily: "var(--font-mono)", fontSize: "11px", color: on ? "var(--color-primary-ink)" : "var(--color-ink-faint)",
  background: on ? "var(--color-primary-soft)" : "var(--color-surface-sunken)", padding: "1px var(--space-1-5)",
  borderRadius: "var(--radius-full)", minWidth: "18px", textAlign: "center",
});
</script>
