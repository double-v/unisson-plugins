<template>
  <div data-test="denon-formulaire">
    <div style="margin-bottom: var(--space-6)">
      <span style="display: inline-block; margin-left: calc(-1 * var(--space-3))">
        <UiButton intent="ghost" size="sm" @click="emit('retour')"><template #leading><Icone nom="back" /></template>Réveil</UiButton>
      </span>
      <h1 :style="titreH1">{{ id ? `Modifier « ${initiale?.nom || "sans nom"} »` : "Nouvelle alarme" }}</h1>
    </div>

    <Note v-if="erreurServeur.length" ton="danger" role="alert" style="margin-bottom: var(--space-4)">
      <b>Enregistrement refusé par le serveur.</b>
      <span v-for="(m, i) in erreurServeur" :key="i">{{ m }}</span>
    </Note>

    <UiSkeleton v-if="id && !initiale && !erreurChargement" :rows="4" :cols="1" />
    <UiErrorState v-else-if="erreurChargement" :message="erreurChargement" retry-label="Revenir à la liste" @retry="emit('retour')" />

    <UiPanel v-else as="form" padding="md" novalidate @submit.prevent="enregistrer">
      <div style="display: flex; flex-direction: column">
        <!-- Quand -->
        <div :style="bloc(0)">
          <h2 :style="titreBloc">Quand</h2>
          <div :style="{ display: 'grid', gap: 'var(--space-4)', gridTemplateColumns: etroit ? '1fr' : 'minmax(0,2fr) minmax(8rem,1fr)' }">
            <UiField :model-value="e.nom" label="Nom" placeholder="Semaine" :error="er.nom" @update:model-value="champ('nom', $event)" />
            <UiField :model-value="e.heure" label="Heure" type="time" :error="er.heure" :hint="`Heure de ${etat.fuseau}`"
              @update:model-value="champ('heure', $event)" />
          </div>
          <div style="display: flex; flex-direction: column; gap: var(--space-1-5)">
            <span :style="libelle">Jours</span>
            <div role="group" aria-label="Jours" style="display: flex; flex-wrap: wrap; gap: var(--space-1-5); align-items: center">
              <span v-for="(j, i) in JOURS" :key="i" style="display: inline-flex; width: var(--space-9)">
                <UiChip interactive :pressed="!!(e.jours & (1 << i))" :aria-label="JOURS_LONGS[i]" style="width: 100%; justify-content: center; padding: 0"
                  @click="champ('jours', e.jours ^ (1 << i))">{{ j }}</UiChip>
              </span>
              <span aria-hidden="true" style="width: 1px; height: 20px; background: var(--color-border); margin: 0 var(--space-1)" />
              <UiChip v-for="[v, l] in RACCOURCIS" :key="v" interactive :pressed="e.jours === v" @click="champ('jours', v)">{{ l }}</UiChip>
            </div>
            <span v-if="er.jours" :style="erreurStyle">{{ er.jours }}</span>
            <span v-else :style="indice">{{ e.jours === 0 ? "Une seule fois : l'alarme se désactive après son passage. " : "" }}<template
              v-if="!e.active">Désactivée : elle ne sonnera pas.</template><template v-else-if="apercu">Prochaine : <b style="color: var(--color-ink)">{{ apercu }}</b></template></span>
          </div>
          <div style="display: flex; align-items: center; gap: var(--space-3)">
            <UiSwitch :model-value="e.active" aria-labelledby="denon-lib-active" @update:model-value="champ('active', $event)" />
            <span id="denon-lib-active">Active</span>
          </div>
        </div>

        <!-- Ce qui se joue -->
        <div :style="bloc(1)">
          <h2 :style="titreBloc">Ce qui se joue</h2>
          <div role="radiogroup" aria-label="Ce qui se joue" :style="choix">
            <button v-for="o in CONTEXTES" :key="o.v" type="button" role="radio" :aria-checked="e.contexte === o.v" :style="option(e.contexte === o.v)"
              @click="choisirContexte(o.v)">
              <b style="font-weight: 600; font-size: var(--text-sm)">{{ o.titre }}</b>
              <span :style="{ fontSize: 'var(--text-xs)', color: e.contexte === o.v ? 'var(--color-primary-ink)' : 'var(--color-ink-muted)' }">{{ o.sous }}</span>
            </button>
          </div>
          <div style="padding: var(--space-4); background: var(--color-surface-sunken); border-radius: var(--radius-md); display: flex; flex-direction: column; gap: var(--space-4)">
            <!-- une playlist -->
            <div v-if="e.contexte === 'playlist'" :style="rangee">
              <div :style="colonne">
                <UiSelect :model-value="e.contexte_id ?? ''" label="Playlist" block @update:model-value="champ('contexte_id', $event === '' ? null : +$event)">
                  <option value="">{{ playlists === null ? "Chargement…" : playlists.length ? "Choisir une playlist" : "Aucune playlist" }}</option>
                  <option v-for="p in playlists || []" :key="p.id" :value="p.id">{{ p.name }} ({{ p.item_count }} piste{{ p.item_count > 1 ? "s" : "" }})</option>
                </UiSelect>
                <span v-if="er.contexte" :style="erreurStyle">{{ er.contexte }}</span>
                <span v-else-if="playlists && !playlists.length" :style="indice">Créez une playlist dans le player d'abord.</span>
              </div>
              <div :style="colonne">
                <span :style="libelle">Ordre</span>
                <div style="display: flex; flex-wrap: wrap; gap: var(--space-1-5); align-items: center">
                  <UiChip interactive :pressed="!e.melange" @click="champ('melange', false)">Dans l'ordre</UiChip>
                  <UiChip interactive :pressed="e.melange" @click="champ('melange', true)">Mélangée</UiChip>
                </div>
              </div>
            </div>

            <!-- la bibliothèque -->
            <template v-else-if="e.contexte === 'bibliotheque'">
              <div :style="rangee">
                <div :style="colonne">
                  <UiSelect :model-value="e.genre_id ?? ''" label="Genre" block @update:model-value="champ('genre_id', $event === '' ? null : +$event)">
                    <option value="">Tous les genres</option>
                    <option v-for="g in genres || []" :key="g.id" :value="g.id">{{ g.name }}</option>
                  </UiSelect>
                  <span v-if="er.genre" :style="erreurStyle">{{ er.genre }}</span>
                </div>
                <div :style="colonne">
                  <UiSelect :model-value="e.format ?? ''" label="Format" block @update:model-value="champ('format', $event || null)">
                    <option value="">Tous les formats</option>
                    <option v-for="f in FORMATS" :key="f" :value="f">{{ f }}</option>
                  </UiSelect>
                  <span v-if="er.format" :style="erreurStyle">{{ er.format }}</span>
                </div>
                <div :style="colonne">
                  <span :style="libelle" id="denon-lib-fav">Favoris</span>
                  <div style="display: flex; align-items: center; gap: var(--space-3); min-height: var(--space-9)">
                    <UiSwitch :model-value="e.favoris" aria-labelledby="denon-lib-fav-texte" @update:model-value="champ('favoris', $event)" />
                    <span id="denon-lib-fav-texte">Favoris seulement</span>
                  </div>
                </div>
              </div>
              <span :style="indice">Le tirage suit les mêmes règles que l'aléatoire du player : il évite ce qui a joué cette semaine.</span>
            </template>

            <!-- un artiste, un album : une recherche -->
            <template v-else>
              <div :style="colonne">
                <UiField :model-value="recherche" :label="e.contexte === 'artiste' ? 'Artiste' : 'Album'"
                  :placeholder="e.contexte === 'artiste' ? 'Chercher un artiste' : 'Chercher un album ou son artiste'"
                  :error="er.contexte" autocomplete="off" @update:model-value="chercher">
                  <template #leading><Icone nom="search" /></template>
                </UiField>
              </div>
              <div v-if="recherche.trim() && !choisi" role="listbox" :aria-label="e.contexte === 'artiste' ? 'Artistes' : 'Albums'"
                style="display: flex; flex-direction: column; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); max-height: 11rem; overflow: auto">
                <span v-if="resultats === null" style="padding: var(--space-3); color: var(--color-ink-faint)">Recherche…</span>
                <span v-else-if="!resultats.length" style="padding: var(--space-3); color: var(--color-ink-faint)">{{ e.contexte === "artiste" ? "Aucun artiste ne correspond." : "Aucun album ne correspond." }}</span>
                <button v-for="(r, i) in resultats || []" :key="r.id" type="button" role="option" :aria-selected="e.contexte_id === r.id"
                  :style="resultatStyle(i, e.contexte_id === r.id)" @click="prendre(r)">
                  <span>{{ r.nom }}</span><span style="color: var(--color-ink-faint); font-family: var(--font-mono)">{{ r.detail }}</span>
                </button>
              </div>
              <span v-else-if="choisi" :style="indice">Tirage dans les pistes {{ e.contexte === "artiste" ? "de l'artiste" : "de l'album" }}, comme l'aléatoire du player.</span>
            </template>
          </div>
        </div>

        <!-- Volume -->
        <div :style="bloc(2)">
          <h2 :style="titreBloc">Volume</h2>
          <div :style="rangee">
            <div :style="curseur">
              <div :style="curseurTete"><label :style="libelle" for="denon-dep">Volume de départ</label><span style="font-family: var(--font-mono)">{{ db(e.volume_depart_db) }}</span></div>
              <input id="denon-dep" type="range" min="-80" max="18" step="0.5" :value="e.volume_depart_db" :aria-valuetext="db(e.volume_depart_db)" :style="range"
                @input="champ('volume_depart_db', +$event.target.value)" />
              <span v-if="er.dep" :style="erreurStyle">{{ er.dep }}</span>
            </div>
            <div :style="curseur">
              <div :style="curseurTete"><label :style="libelle" for="denon-cib">Volume cible</label>
                <span :style="{ fontFamily: 'var(--font-mono)', color: fort ? 'var(--color-warning)' : undefined }">{{ db(e.volume_cible_db) }}</span></div>
              <input id="denon-cib" type="range" min="-80" max="18" step="0.5" :value="e.volume_cible_db" :aria-valuetext="db(e.volume_cible_db)" :style="range"
                @input="champ('volume_cible_db', +$event.target.value)" />
              <span v-if="er.cib" :style="erreurStyle">{{ er.cib }}</span>
              <span v-else-if="fort" :style="{ ...indice, color: 'var(--color-warning)' }">Fort pour un réveil : l'ampli affiche −15 dB comme un volume déjà soutenu.</span>
            </div>
          </div>
          <div :style="curseur">
            <div :style="curseurTete"><label :style="libelle" for="denon-montee">Durée de la montée</label>
              <span style="font-family: var(--font-mono)">{{ e.montee_s === 0 ? "aucune : volume cible d'emblée" : duree(e.montee_s) }}</span></div>
            <div role="group" aria-label="Durées courantes" style="display: flex; flex-wrap: wrap; gap: var(--space-1-5); align-items: center">
              <UiChip v-for="m in PRESETS_MONTEE" :key="m" interactive :pressed="e.montee_s === m" @click="champ('montee_s', m)">{{ m === 0 ? "Aucune" : duree(m) }}</UiChip>
            </div>
            <input id="denon-montee" type="range" min="0" max="3600" step="30" :value="e.montee_s" :aria-valuetext="e.montee_s === 0 ? 'aucune' : duree(e.montee_s)"
              :style="range" @input="champ('montee_s', +$event.target.value)" />
            <svg viewBox="0 0 1000 56" preserveAspectRatio="none" aria-hidden="true" style="width: 100%; height: 56px; display: block">
              <line x1="0" x2="1000" y1="50" y2="50" stroke="var(--color-border)" vector-effect="non-scaling-stroke" />
              <line v-for="x in [250, 500, 750]" :key="x" :x1="x" :x2="x" y1="46" y2="54" stroke="var(--color-border)" vector-effect="non-scaling-stroke" />
              <path :d="courbe" fill="none" stroke="var(--color-primary)" stroke-width="2" vector-effect="non-scaling-stroke" />
            </svg>
            <div aria-hidden="true" style="display: flex; justify-content: space-between; font-family: var(--font-mono); font-size: 11px; color: var(--color-ink-faint); margin-top: calc(-1 * var(--space-1))">
              <span>0</span><span>15 min</span><span>30 min</span><span>45 min</span><span>1 h</span>
            </div>
            <span v-if="er.montee" :style="erreurStyle">{{ er.montee }}</span>
          </div>
          <span :style="indice">Par pas de 0,5 dB. La montée s'arrête si quelqu'un touche au volume.{{ e.volume_depart_db > e.volume_cible_db ? " Le départ est plus fort que la cible : le volume descendra." : "" }}</span>
        </div>

        <!-- Fin -->
        <div :style="bloc(3)">
          <h2 :style="titreBloc">Fin</h2>
          <div role="radiogroup" aria-label="Fin" :style="choix">
            <button v-for="o in FINS" :key="o.v" type="button" role="radio" :aria-checked="e.fin_mode === o.v" :style="option(e.fin_mode === o.v)"
              @click="choisirFin(o.v)">
              <b style="font-weight: 600; font-size: var(--text-sm)">{{ o.titre }}</b>
              <span :style="{ fontSize: 'var(--text-xs)', color: e.fin_mode === o.v ? 'var(--color-primary-ink)' : 'var(--color-ink-muted)' }">{{ o.sous }}</span>
            </button>
          </div>
          <span v-if="e.fin_mode === 'sans_limite'" :style="indice">Le tirage se relance quand il s'épuise. L'ampli reste allumé.</span>
          <div v-else style="max-width: 12rem">
            <!-- L'unité va dans le libellé : UiField n'a pas de suffixe, et la
                 hauteur du champ change au doigt (--touch-min). -->
            <UiField :model-value="e.fin_valeur ?? ''" type="number" min="1" :max="e.fin_mode === 'duree' ? 1440 : 1000"
              :label="e.fin_mode === 'duree' ? 'Durée (min)' : 'Nombre de pistes'" :error="er.fin" block
              @update:model-value="champ('fin_valeur', $event === '' ? null : Number($event))" />
          </div>
          <span :style="indice">Pour couper le réveil : « Arrêter », la veille, une autre entrée, la sourdine ou la pause. L'ampli lâche parfois la lecture seul : un Stop en milieu de piste, même à la télécommande, est relancé deux fois.</span>
        </div>
      </div>

      <template #footer>
        <div style="display: flex; flex-wrap: wrap; gap: var(--space-2); justify-content: flex-end; align-items: center; width: 100%">
          <span style="flex: 1; min-width: 14rem; font-size: var(--text-sm); color: var(--color-ink-muted)">
            <b style="color: var(--color-ink); font-weight: 600">{{ e.heure ? hm(e.heure) : "—" }}</b> {{ resume }}
          </span>
          <span :style="{ display: 'inline-flex', flex: etroit ? 1 : undefined }"><UiButton intent="ghost" size="md" block @click="emit('retour')">Annuler</UiButton></span>
          <span :style="{ display: 'inline-flex', flex: etroit ? 1 : undefined }"><UiButton intent="primary" size="md" type="submit" block :loading="envoi">Enregistrer</UiButton></span>
        </div>
      </template>
    </UiPanel>
  </div>
</template>

<script setup>
// Le formulaire d'une alarme, sur sa page (« ‹ Réveil » pour revenir) :
// quand, ce qui se joue, le volume qui monte (avec sa courbe), et la fin.
// Les refus du serveur (422) s'affichent champ par champ.
import { computed, onMounted, reactive, ref } from "vue";
import { UiButton, UiChip, UiErrorState, UiField, UiPanel, UiSelect, UiSkeleton, UiSwitch } from "@ds/primitives";
import Icone from "./Icone.vue";
import Note from "./Note.vue";
import { coeur, nomAlbum, nomArtiste, reveil } from "./api.js";
import { chargerAlarmes, chargerGenres, chargerPlaylists, etat, quoi } from "./etat.js";
import { FORMATS, JOURS, JOURS_LONGS, PRESETS_MONTEE, SEUIL_FORT_DB, db, duree, fin, hm, libJours, prochaineApercu } from "./outils.js";

const props = defineProps({ id: { type: Number, default: null }, etroit: Boolean });
const emit = defineEmits(["retour", "enregistree"]);

const RACCOURCIS = [[31, "Semaine"], [96, "Week-end"], [127, "Tous"], [0, "Une seule fois"]];
const CONTEXTES = [
  { v: "playlist", titre: "Une playlist", sous: "dans l'ordre ou mélangée" },
  { v: "bibliotheque", titre: "La bibliothèque", sous: "tirage, avec filtres" },
  { v: "artiste", titre: "Un artiste", sous: "tirage dans ses pistes" },
  { v: "album", titre: "Un album", sous: "tirage dans ses pistes" },
];
const FINS = [
  { v: "duree", titre: "Après une durée", sous: "puis veille de l'ampli" },
  { v: "pistes", titre: "Après un nombre de pistes", sous: "puis veille de l'ampli" },
  { v: "sans_limite", titre: "Sans limite", sous: "jusqu'à ce qu'on arrête" },
];
const CHAMPS = ["nom", "active", "heure", "jours", "contexte", "contexte_id", "melange", "genre_id", "format", "favoris",
  "volume_depart_db", "volume_cible_db", "montee_s", "fin_mode", "fin_valeur"];
// Le champ du serveur → l'endroit du formulaire où dire le refus.
const OU = {
  nom: "nom", heure: "heure", jours: "jours", contexte: "contexte", contexte_id: "contexte", melange: "contexte",
  genre_id: "genre", format: "format", favoris: "contexte", volume_depart_db: "dep", volume_cible_db: "cib",
  montee_s: "montee", fin_mode: "fin", fin_valeur: "fin",
};

const e = reactive({
  nom: "", active: true, heure: "07:00", jours: 31, contexte: "playlist", contexte_id: null, melange: false,
  genre_id: null, format: null, favoris: false, volume_depart_db: -50, volume_cible_db: -32, montee_s: 120,
  fin_mode: "duree", fin_valeur: 30,
});
const er = reactive({});
const erreurServeur = ref([]);
const erreurChargement = ref("");
const initiale = ref(null);
const envoi = ref(false);
const playlists = ref(null);
const genres = ref(null);
const recherche = ref("");
const resultats = ref(null);
const choisi = ref(false);

onMounted(async () => {
  // Relues à chaque ouverture : une playlist ou un genre a pu naître depuis.
  chargerPlaylists({ frais: true }).then((l) => {
    playlists.value = l;
    if (!props.id && e.contexte === "playlist" && e.contexte_id == null && l.length) e.contexte_id = premierePlaylist(l);
    if (!props.id && !l.length) e.contexte = "bibliotheque";
  });
  chargerGenres({ frais: true }).then((l) => { genres.value = l; });
  if (props.id) {
    // La liste est relue : l'alarme a pu changer, ou disparaître, ailleurs.
    await chargerAlarmes();
    const a = (etat.alarmes || []).find((x) => x.id === props.id);
    if (!a) {
      erreurChargement.value = etat.erreurListe ? etat.erreurListe.message : "Cette alarme n'existe plus.";
      return;
    }
    for (const c of CHAMPS) e[c] = a[c];
    initiale.value = a;
    if (a.contexte === "artiste" && a.contexte_id) {
      const r = etat.refs.artistes[a.contexte_id];
      recherche.value = r?.nom || "";
      choisi.value = true;
      if (!r) coeur.artiste(a.contexte_id).then((x) => { recherche.value = nomArtiste(x); }).catch(() => {});
    } else if (a.contexte === "album" && a.contexte_id) {
      const r = etat.refs.albums[a.contexte_id];
      recherche.value = r?.nom || "";
      choisi.value = true;
      if (!r) coeur.album(a.contexte_id).then((x) => { recherche.value = nomAlbum(x); }).catch(() => {});
    }
  }
});

// Une playlist qui a des pistes, de préférence : une vide n'a rien à jouer.
const premierePlaylist = (l) => (l.find((p) => p.item_count > 0) || l[0])?.id ?? null;

// Une alarme « une seule fois » déjà passée s'est désactivée d'elle-même :
// lui donner une autre heure ou d'autres jours, c'est la reprogrammer.
const uniquePassee = computed(() => {
  const a = initiale.value;
  return !!a && a.jours === 0 && !a.active && !!a.derniere_echeance;
});

function champ(nom, valeur) {
  e[nom] = valeur;
  delete er[OU[nom]];
  if ((nom === "heure" || nom === "jours") && uniquePassee.value && !e.active) e.active = true;
}

function choisirContexte(v) {
  if (e.contexte === v) return;
  e.contexte = v;
  e.contexte_id = v === "playlist" ? premierePlaylist(playlists.value || []) : null;
  recherche.value = "";
  resultats.value = null;
  choisi.value = false;
  delete er.contexte;
}

function choisirFin(v) {
  if (e.fin_mode === v) return;
  e.fin_mode = v;
  e.fin_valeur = v === "duree" ? 30 : v === "pistes" ? 5 : null;
  delete er.fin;
}

let minuterie = null;
function chercher(q) {
  recherche.value = q;
  choisi.value = false;
  e.contexte_id = null;
  delete er.contexte;
  clearTimeout(minuterie);
  resultats.value = null;
  if (!q.trim()) return;
  const contexte = e.contexte;
  minuterie = setTimeout(async () => {
    try {
      const l = contexte === "artiste"
        ? (await coeur.artistes(q.trim())).map((a) => ({
          id: a.id, nom: nomArtiste(a), detail: a.track_count ? `${a.track_count} pistes` : `${a.album_count ?? 0} album${a.album_count > 1 ? "s" : ""}`,
        }))
        : (await coeur.albums(q.trim())).map((a) => ({ id: a.id, nom: a.name, detail: a.artist_name, artiste: a.artist_name }));
      // La recherche a pu changer pendant l'appel : on ne montre que la dernière.
      if (recherche.value === q && e.contexte === contexte) resultats.value = l;
    } catch {
      if (recherche.value === q) resultats.value = [];
    }
  }, 200);
}

function prendre(r) {
  e.contexte_id = r.id;
  recherche.value = r.nom;
  choisi.value = true;
  if (e.contexte === "artiste") etat.refs.artistes[r.id] = { id: r.id, nom: r.nom };
  else etat.refs.albums[r.id] = { id: r.id, nom: r.nom, artiste: r.artiste || "" };
  delete er.contexte;
}

const fort = computed(() => e.volume_cible_db > SEUIL_FORT_DB);
const apercu = computed(() => {
  void etat.maintenant;
  return prochaineApercu(e.heure, e.jours, etat.fuseau);
});
const courbe = computed(() => {
  const y = (v) => 50 - ((v + 80) / 98) * 44;
  const x = (e.montee_s / 3600) * 1000;
  return `M0 ${y(e.volume_depart_db)} L${x} ${y(e.volume_cible_db)} L1000 ${y(e.volume_cible_db)}`;
});
const resume = computed(() => {
  const [l1, l2] = quoi(e);
  return `${libJours(e.jours)} · ${l1} (${l2}) · ${db(e.volume_depart_db)} → ${db(e.volume_cible_db)}${e.montee_s ? ` en ${duree(e.montee_s)}` : ""} · ${fin(e)}`;
});

// ── l'enregistrement ─────────────────────────────────────────────────────
function valider() {
  const x = {};
  if (!e.nom.trim()) x.nom = "Donnez un nom à l'alarme, par exemple « Semaine ».";
  if (!/^\d{2}:\d{2}(:\d{2})?$/.test(e.heure || "")) x.heure = "Heure attendue au format HH:MM.";
  if (e.contexte === "playlist") {
    if (e.contexte_id == null) x.contexte = "Choisissez une playlist.";
    else if (playlists.value?.find((p) => p.id === e.contexte_id)?.item_count === 0) x.contexte = "Cette playlist est vide : l'alarme n'aurait rien à jouer.";
  }
  if ((e.contexte === "artiste" || e.contexte === "album") && !e.contexte_id) x.contexte = e.contexte === "artiste" ? "Choisissez un artiste." : "Choisissez un album.";
  if (e.fin_mode !== "sans_limite" && !(Number.isInteger(e.fin_valeur) && e.fin_valeur > 0)) x.fin = "Indiquez un nombre entier supérieur à 0.";
  return x;
}

function corps() {
  const c = Object.fromEntries(CHAMPS.map((k) => [k, e[k]]));
  if (c.contexte !== "playlist") c.melange = false;
  if (c.contexte !== "bibliotheque") Object.assign(c, { genre_id: null, format: null, favoris: false });
  if (c.contexte === "bibliotheque") c.contexte_id = null;
  if (c.fin_mode === "sans_limite") c.fin_valeur = null;
  return c;
}

const majuscule = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

async function enregistrer() {
  for (const k of Object.keys(er)) delete er[k];
  erreurServeur.value = [];
  Object.assign(er, valider());
  if (Object.keys(er).length) return;
  envoi.value = true;
  try {
    if (props.id) await reveil.modifier(props.id, corps());
    else await reveil.creer(corps());
    await chargerAlarmes();
    emit("enregistree");
  } catch (x) {
    if (x.statut === 422 && x.erreurs.length) {
      const ailleurs = [];
      for (const { champ: c, message } of x.erreurs) {
        const ou = OU[c];
        if (ou) er[ou] = er[ou] ? `${er[ou]} ; ${message}` : `${majuscule(message)}.`;
        else ailleurs.push(`${c || "corps"} : ${message}`);
      }
      erreurServeur.value = ailleurs.length ? ailleurs : ["Corrigez les champs signalés (422)."];
    } else if (x.code === "alarme_introuvable") {
      // Supprimée ailleurs pendant qu'on la modifiait.
      erreurServeur.value = ["Cette alarme n'existe plus : elle a été supprimée entre-temps."];
      chargerAlarmes();
    } else {
      erreurServeur.value = [x.message];
    }
  } finally {
    envoi.value = false;
  }
}

// ── le dessin ────────────────────────────────────────────────────────────
const titreH1 = {
  fontFamily: "var(--font-display)", fontSize: "var(--text-3xl)", lineHeight: "var(--text-3xl-lh)",
  letterSpacing: "var(--text-3xl-ls)", fontWeight: 600, margin: "var(--space-1) 0 0",
};
const bloc = (i) => ({
  display: "flex", flexDirection: "column", gap: "var(--space-3)",
  borderTop: i ? "1px solid var(--color-border)" : undefined,
  paddingTop: i ? "var(--space-6)" : undefined, marginTop: i ? "var(--space-6)" : undefined,
});
const titreBloc = { fontFamily: "var(--font-sans)", lineHeight: "var(--text-xs-lh)", fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--color-ink-muted)", margin: 0 };
const libelle = { fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".04em", color: "var(--color-ink-muted)" };
const indice = { fontSize: "var(--text-xs)", color: "var(--color-ink-faint)" };
const erreurStyle = { fontSize: "var(--text-xs)", color: "var(--color-danger)" };
const rangee = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "var(--space-4)" };
const colonne = { display: "flex", flexDirection: "column", gap: "var(--space-1-5)", minWidth: 0 };
const choix = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "var(--space-2)" };
const option = (on) => ({
  display: "flex", flexDirection: "column", gap: "2px", textAlign: "left", padding: "var(--space-3)",
  border: `1px solid var(--color-${on ? "primary" : "border-strong"})`, borderRadius: "var(--radius-md)",
  background: on ? "var(--color-primary-soft)" : "var(--color-surface)", cursor: "pointer", font: "inherit",
  color: on ? "var(--color-primary-ink)" : "var(--color-ink)", minHeight: "var(--touch-min)",
  boxShadow: on ? "inset 0 0 0 1px var(--color-primary)" : undefined,
});
const curseur = { display: "flex", flexDirection: "column", gap: "var(--space-1-5)" };
const curseurTete = { display: "flex", justifyContent: "space-between", alignItems: "baseline" };
const range = { width: "100%", accentColor: "var(--color-primary)", minHeight: "var(--touch-min)" };
const resultatStyle = (i, on) => ({
  all: "unset", cursor: "pointer", padding: "var(--space-2) var(--space-3)", display: "flex", justifyContent: "space-between",
  gap: "var(--space-2)", minHeight: "var(--touch-min)", alignItems: "center",
  borderTop: i ? "1px solid var(--color-border)" : undefined,
  background: on ? "var(--color-primary-soft)" : undefined, color: on ? "var(--color-primary-ink)" : undefined,
});
</script>
