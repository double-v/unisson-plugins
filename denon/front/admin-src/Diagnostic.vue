<template>
  <UiSkeleton v-if="!d && !etat.erreurDiagnostic" :rows="3" :cols="1" />
  <UiErrorState v-else-if="!d" :message="`Le diagnostic n'a pas pu être lu : ${etat.erreurDiagnostic.message}`"
    retry-label="Réessayer" @retry="relancer" />

  <div v-else data-test="denon-diagnostic" style="display: flex; flex-direction: column; gap: var(--space-6)">
    <!-- l'ampli -->
    <UiPanel title="L'ampli" title-tag="h3" padding="md">
      <template #header><p :style="sousTitre">{{ d.pilote.libelle }} · <span style="font-family: var(--font-mono)">{{ d.telnet.hote || "hôte non réglé" }}</span></p></template>
      <template #actions><UiButton intent="secondary" size="sm" :loading="charge" @click="relancer">Relancer le diagnostic</UiButton></template>
      <div style="margin: calc(-1 * var(--space-1)) calc(-1 * var(--space-4)) calc(-1 * var(--space-4))">
        <div :style="ligne(0)">
          <div :style="nomStyle"><span :style="point(d.telnet.connecte ? 'success' : 'danger')" />Telnet</div>
          <div :style="valStyle">
            <template v-if="d.telnet.connecte">
              <UiChip tone="success" dot>Connecté</UiChip>
              <span :style="trace">{{ d.telnet.hote }}:{{ d.telnet.port }}{{ etatAmpli }}</span>
            </template>
            <template v-else>
              <UiChip tone="danger" dot>Déconnecté</UiChip>
              <span v-if="!d.telnet.hote" :style="muet">Aucun hôte réglé : renseignez l'adresse IP de l'ampli dans les réglages du plugin (Plugins › Denon).</span>
              <span v-else :style="muet">Pas de réponse de <span style="font-family: var(--font-mono)">{{ d.telnet.hote }}:{{ d.telnet.port }}</span>. L'ampli est peut-être en veille profonde : voir le premier conseil.</span>
            </template>
          </div>
        </div>
        <div :style="ligne(1)">
          <div :style="nomStyle"><span :style="point(d.upnp.joignable ? 'success' : 'danger')" />Lecteur UPnP</div>
          <div :style="valStyle">
            <template v-if="d.upnp.joignable">
              <UiChip tone="success" dot>Joignable</UiChip>
              <span :style="trace">{{ d.upnp.description }}</span>
            </template>
            <template v-else>
              <UiChip tone="danger" dot>Muet</UiChip>
              <span v-if="d.upnp.description" :style="muet">Aucune réponse sur <span style="font-family: var(--font-mono)">{{ d.upnp.description }}</span>.</span>
              <span v-else :style="muet">Aucune adresse : le lecteur se cherche sur l'hôte de l'ampli, port 8080.</span>
              <span v-if="d.upnp.erreur" :style="trace">{{ d.upnp.erreur }}</span>
            </template>
          </div>
        </div>
        <div :style="ligne(2)">
          <div :style="nomStyle"><span :style="point(d.adresse_reseau.reglee ? 'success' : 'warning')" />Adresse d'unisson</div>
          <div :style="valStyle">
            <template v-if="d.adresse_reseau.reglee">
              <UiChip tone="success" dot>Réglée</UiChip>
              <span :style="trace">{{ d.adresse_reseau.adresse }}</span>
            </template>
            <template v-else>
              <UiChip tone="warning" dot>Non réglée</UiChip>
              <span :style="muet">L'ampli va chercher la musique lui-même : il lui faut l'adresse d'unisson sur le réseau local.</span>
              <UiButton intent="secondary" size="sm" :to="d.adresse_reseau.reglage.replace(/^\/admin/, '')">
                <template #leading><Icone nom="link" /></template>Régler dans Réglages › Réseau
              </UiButton>
            </template>
          </div>
        </div>
        <div :style="ligne(3)">
          <div :style="nomStyle"><span :style="point(formats.length ? 'success' : 'warning')" />Formats</div>
          <div :style="valStyle">
            <template v-if="formats.length">
              <div style="display: flex; flex-wrap: wrap; gap: var(--space-1)">
                <UiChip v-for="f in formats" :key="f" tone="neutral">{{ f }}</UiChip>
              </div>
              <span :style="{ ...muet, color: 'var(--color-ink-faint)', fontSize: 'var(--text-xs)' }">Annoncés par <span style="font-family: var(--font-mono)">GetProtocolInfo</span>.{{ plafond }}</span>
            </template>
            <span v-else style="color: var(--color-ink-faint)">Inconnus tant que le lecteur UPnP ne répond pas.</span>
          </div>
        </div>
      </div>
    </UiPanel>

    <!-- l'heure et le testeur de fuseau -->
    <UiPanel title="L'heure" title-tag="h3" padding="md">
      <template #header><p :style="sousTitre">Les alarmes suivent l'heure du serveur, dans le fuseau réglé.</p></template>
      <div style="display: flex; flex-direction: column; gap: var(--space-4)">
        <div style="display: flex; flex-direction: column; gap: var(--space-1-5); max-width: 18rem">
          <UiSelect :model-value="etat.fuseau" label="Fuseau" :disabled="reglage" block @update:model-value="changerFuseau">
            <option v-for="f in fuseaux" :key="f" :value="f">{{ f === "Europe/Paris" ? "Europe/Paris (par défaut)" : f }}</option>
          </UiSelect>
          <span v-if="erreurReglage" :style="{ ...indice, color: 'var(--color-danger)' }">{{ erreurReglage }}</span>
          <span v-else :style="indice">Réglage du plugin, utilisé pour toutes les alarmes.</span>
        </div>
        <Note v-if="etat.avertissementFuseau" ton="warning" role="alert"><span>{{ etat.avertissementFuseau }}</span></Note>

        <div :style="{ display: 'grid', gridTemplateColumns: etroit ? '1fr' : 'repeat(3, minmax(0, 1fr))', gap: 'var(--space-3)' }">
          <div v-for="h in horloges" :key="h.lib" :style="horloge">
            <span style="font-size: 11px; font-weight: 600; letter-spacing: .04em; color: var(--color-ink-muted)">{{ h.lib }}</span>
            <span style="font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: var(--text-xl); font-weight: 500; letter-spacing: -0.02em">{{ h.h }}</span>
            <span style="font-size: var(--text-xs); color: var(--color-ink-faint); font-family: var(--font-mono)">{{ h.s }}</span>
          </div>
        </div>
        <div v-if="!alerteEcart" style="display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center">
          <UiChip tone="success" dot>Écart : {{ libEcart(ecart) }}</UiChip>
          <span style="font-size: var(--text-xs); color: var(--color-ink-faint)">Comparé à l'heure de ce navigateur ({{ navTz }}).</span>
        </div>
        <Note v-else ton="warning" role="alert">
          <b>L'horloge ou le fuseau du serveur ne correspond pas.</b>
          <span>Le serveur est {{ ecart > 0 ? "en avance" : "en retard" }} de {{ libEcart(ecart) }} sur ce navigateur. Les alarmes partiront à l'heure du serveur. Vérifiez le fuseau, ou la synchronisation NTP de la machine.</span>
          <span style="font-size: var(--text-xs); color: var(--color-ink-faint)">Comparé à l'heure de ce navigateur ({{ navTz }}).</span>
        </Note>

        <div style="display: flex; flex-direction: column; gap: var(--space-2-5)">
          <h4 style="font-family: var(--font-sans); line-height: var(--text-xs-lh); font-size: var(--text-xs); font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: var(--color-ink-muted); margin: 0">Tester le fuseau</h4>
          <p style="margin: 0; max-width: 62ch; color: var(--color-ink-muted)">{{ descriptionTest }}</p>
          <div style="display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center">
            <UiButton v-for="n in [5, 10]" :key="n" intent="secondary" size="md" :disabled="testEnAttente" :loading="lancement === n" @click="tester(n)">
              <template #leading><Icone nom="clock" /></template>Tester dans {{ n }} s
            </UiButton>
          </div>
          <Note v-if="erreurTest" ton="danger" role="alert"><span>{{ erreurTest }}</span></Note>
          <div v-if="t" aria-live="polite" style="display: flex; flex-direction: column; gap: var(--space-2)">
            <span style="font-size: var(--text-xs); color: var(--color-ink-faint)">Dernier test{{ t.etat !== "en_attente" && t.retiree ? " (ligne retirée de la liste, le résultat reste ici jusqu'au test suivant)" : "" }}</span>
            <div style="display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center">
              <UiChip v-if="t.etat === 'en_attente'" tone="accent" dot>{{ reste ? `part dans ${reste} s` : "échéance passée, on attend…" }}</UiChip>
              <UiChip v-else-if="t.etat === 'partie'" tone="success" dot>partie à {{ t.heure }}, avec {{ virgule((t.retardMs || 0) / 1000) }} s de retard</UiChip>
              <UiChip v-else tone="danger" dot>pas partie : attendue à {{ t.heure }}</UiChip>
              <span v-if="t.etat === 'partie'" :style="muet">{{ suite ? `L'heure est bonne, ${suite}.` : "Le fuseau et l'horloge sont bons." }}</span>
            </div>
            <div style="font-family: var(--font-mono); font-size: 12px; color: var(--color-ink-muted); display: flex; flex-wrap: wrap; gap: var(--space-1) var(--space-4)">
              <span>créée « {{ t.nom }} »</span><span>serveur {{ t.trace.serveur }} {{ t.trace.decalage }}</span><span>UTC {{ t.trace.utc }}</span><span>échéance {{ t.heure }}</span>
            </div>
            <Note v-if="t.etat === 'pas_partie' || t.etat === 'manquee'" ton="danger">
              <span>L'ordonnanceur n'a pas déclenché l'alarme. Vérifiez le fuseau ci-dessus, puis les journaux <span style="font-family: var(--font-mono)">unisson.plugin.denon</span>.</span>
            </Note>
          </div>
        </div>
      </div>
    </UiPanel>

    <!-- les conseils -->
    <UiPanel title="Réglages de l'ampli" title-tag="h3" padding="md">
      <template #header><p :style="sousTitre">À faire une fois, sur l'ampli et sur la box.</p></template>
      <ul style="margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: var(--space-3)">
        <li v-for="c in d.conseils" :key="c.code" style="display: flex; gap: var(--space-3); align-items: flex-start">
          <span style="margin-top: 3px; color: var(--color-accent); display: inline-flex"><Icone nom="info" /></span>
          <div>
            <b v-if="TITRES[c.code]" style="font-weight: 600">{{ TITRES[c.code] }}</b> {{ c.message }}
            <template v-if="c.code === 'ip_fixe' && d.telnet.hote"><br><span style="color: var(--color-ink-faint)">Adresse actuelle : <span style="font-family: var(--font-mono)">{{ d.telnet.hote }}</span></span></template>
          </div>
        </li>
      </ul>
    </UiPanel>
  </div>
</template>

<script setup>
// Le diagnostic : ce qui répond (telnet, UPnP, adresse d'unisson, formats),
// l'heure du serveur comparée à celle de ce navigateur, le testeur de
// fuseau, et les réglages à faire une fois sur l'ampli.
import { computed, ref } from "vue";
import { UiButton, UiChip, UiErrorState, UiPanel, UiSelect, UiSkeleton } from "@ds/primitives";
import Icone from "./Icone.vue";
import Note from "./Note.vue";
import { reveil } from "./api.js";
import { chargerAlarmes, chargerDiagnostic, etat, lancerTest, serveurMaintenant, suiteDuTest } from "./etat.js";
import { FUSEAUX, db, decalage, formatsCourts, fuseauNavigateur, hms, libEcart, murale, virgule } from "./outils.js";

const props = defineProps({ etroit: Boolean });

const d = computed(() => etat.diagnostic);
const t = computed(() => etat.test);
const charge = ref(false);
const reglage = ref(false);
const erreurReglage = ref("");
const erreurTest = ref("");
const lancement = ref(null);
const navTz = fuseauNavigateur();

const TITRES = {
  controle_reseau: "Garder le contrôle réseau en veille.",
  ip_fixe: "Donner une IP fixe à l'ampli.",
};

async function relancer() {
  charge.value = true;
  await chargerDiagnostic();
  charge.value = false;
}

const formats = computed(() => formatsCourts(d.value?.upnp?.formats));
const plafond = computed(() => {
  const p = d.value?.pilote?.plafond;
  if (!p) return "";
  const bits = p.profondeur_max ? `${p.profondeur_max} bits` : "";
  const khz = p.frequence_max ? `${virgule(p.frequence_max / 1000, p.frequence_max % 1000 ? 1 : 0)} kHz` : "";
  return ` Plafond du pilote : ${[bits, khz].filter(Boolean).join(" / ")} ; au-delà, unisson convertit.`;
});
const etatAmpli = computed(() => {
  const tl = d.value.telnet;
  const parts = [];
  if (tl.alimentation === true) parts.push("allumé");
  else if (tl.alimentation === false) parts.push("en veille");
  if (tl.source) parts.push(`source ${tl.source}`);
  if (tl.volume != null) parts.push(db(tl.volume));
  return parts.length ? ` · ${parts.join(" · ")}` : "";
});

// ── l'heure ──────────────────────────────────────────────────────────────
const fuseaux = computed(() => (FUSEAUX.includes(etat.fuseau) ? FUSEAUX : [etat.fuseau, ...FUSEAUX]));
const horloges = computed(() => {
  void etat.maintenant; // la seconde qui passe
  const sn = serveurMaintenant(), nav = new Date();
  return [
    { lib: `Serveur, ${etat.fuseau}`, h: hms(sn, etat.fuseau), s: decalage(sn, etat.fuseau) },
    { lib: "Serveur, UTC", h: hms(sn, "UTC"), s: "+00:00" },
    { lib: "Ce navigateur", h: hms(nav, navTz), s: `${navTz} ${decalage(nav, navTz)}` },
  ];
});
const ecart = computed(() => {
  void etat.maintenant;
  if (etat.decalageServeurMs == null) return 0;
  return (murale(serveurMaintenant(), etat.fuseau) - murale(new Date(), navTz)) / 1000;
});
const alerteEcart = computed(() => Math.abs(ecart.value) > 60);

async function changerFuseau(f) {
  if (f === etat.fuseau) return;
  reglage.value = true;
  erreurReglage.value = "";
  try {
    await reveil.regler({ fuseau: f });
    await Promise.all([chargerDiagnostic(), chargerAlarmes()]);
  } catch (e) {
    erreurReglage.value = `Le fuseau n'a pas pu être réglé : ${e.message}`;
  } finally {
    reglage.value = false;
  }
}

// ── le testeur ───────────────────────────────────────────────────────────
const modele = computed(() => {
  const l = (etat.alarmes || []).filter((a) => !a.test);
  return l.length ? l.reduce((a, b) => (a.id < b.id ? a : b)) : null;
});
const descriptionTest = computed(() => (modele.value
  ? `Crée une alarme unique qui part par l'ordonnanceur, comme une vraie, avec ce que joue « ${modele.value.nom} » et ses volumes, fin après 1 piste. Elle se retire seule après son passage.`
  : "Crée une alarme unique qui part par l'ordonnanceur, comme une vraie : un tirage de la bibliothèque à −50 dB, fin après 1 piste. Elle se retire seule après son passage."));
const testEnAttente = computed(() => t.value?.etat === "en_attente");
const reste = computed(() => Math.max(0, Math.ceil((t.value.echeanceMs - etat.maintenant) / 1000)));
const suite = computed(() => suiteDuTest(t.value));

async function tester(n) {
  lancement.value = n;
  erreurTest.value = "";
  try {
    await lancerTest(n);
  } catch (e) {
    erreurTest.value = e.erreurs?.length ? e.erreurs.map((x) => x.message).join(" ; ") : e.message;
  } finally {
    lancement.value = null;
  }
}

// ── le dessin ────────────────────────────────────────────────────────────
const ligne = (i) => ({
  display: "grid",
  gridTemplateColumns: props.etroit ? "1fr" : "11rem minmax(0, 1fr)",
  gap: "var(--space-2) var(--space-4)",
  padding: "var(--space-3) var(--space-4)",
  alignItems: "start",
  borderTop: i ? "1px solid var(--color-border)" : undefined,
});
const nomStyle = { fontWeight: 600, display: "flex", alignItems: "center", gap: "var(--space-2)" };
const valStyle = { display: "flex", flexDirection: "column", gap: "var(--space-1-5)", alignItems: "flex-start", minWidth: 0 };
const point = (ton) => ({ width: "8px", height: "8px", borderRadius: "50%", flex: "0 0 auto", background: `var(--color-${ton})` });
const trace = { fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--color-ink-faint)", overflowWrap: "anywhere" };
const muet = { color: "var(--color-ink-muted)" };
const sousTitre = { margin: 0, color: "var(--color-ink-muted)", fontSize: "var(--text-sm)" };
const indice = { fontSize: "var(--text-xs)", color: "var(--color-ink-faint)" };
const horloge = {
  padding: "var(--space-3)", background: "var(--color-surface-sunken)", borderRadius: "var(--radius-md)",
  display: "flex", flexDirection: "column", gap: "2px",
};
</script>
