// L'état partagé de la page Réveil : la liste, la séance, le diagnostic,
// l'horloge du serveur et le testeur de fuseau. Un seul objet réactif, pour
// que le résultat d'un test se lise à deux endroits (la ligne « Test » de la
// liste et la carte « L'heure » du diagnostic).
import { reactive } from "vue";
import { coeur, nomAlbum, nomArtiste, reveil } from "./api.js";
import { heureDe, resultat } from "./outils.js";

// La ligne de test reste 60 s dans la liste après son résultat (choix de
// l'opérateur) ; sans départ 10 s après l'échéance, on la dit « pas partie ».
export const GARDE_TEST_MS = 60_000;
const ATTENTE_DEPART_MS = 10_000;

export const etat = reactive({
  fuseau: "Europe/Paris",
  avertissementFuseau: null,
  alarmes: null, // null : pas encore chargées
  erreurListe: null,
  seance: null,
  derniere: null,
  diagnostic: null,
  erreurDiagnostic: null,
  // L'horloge : l'écart entre l'heure du serveur et celle de ce navigateur,
  // mesuré au dernier appel (corrigé de la moitié de l'aller-retour).
  decalageServeurMs: null,
  test: null, // { id, nom, heure, echeanceMs, etat, retardMs, resultat, trace, retraitMs }
  refs: { playlists: {}, artistes: {}, albums: {}, genres: {} },
  maintenant: Date.now(),
});

export const serveurMaintenant = () => new Date(Date.now() + (etat.decalageServeurMs || 0));

function noterHorloge(h, avantMs, apresMs) {
  if (!h) return;
  etat.fuseau = h.fuseau || etat.fuseau;
  etat.avertissementFuseau = h.avertissement || null;
  const utc = Date.parse(h.utc);
  if (!Number.isNaN(utc)) etat.decalageServeurMs = utc - (avantMs + apresMs) / 2;
}

export async function chargerAlarmes() {
  try {
    const r = await reveil.alarmes();
    etat.fuseau = r.fuseau || etat.fuseau;
    etat.avertissementFuseau = r.avertissement || null;
    etat.alarmes = r.alarmes;
    etat.erreurListe = null;
    completerRefs(r.alarmes);
  } catch (e) {
    etat.erreurListe = e;
  }
}

export async function chargerSeance() {
  try {
    const r = await reveil.seance();
    etat.seance = r.seance;
    etat.derniere = r.derniere;
  } catch {
    // La bannière se tait : la liste dit déjà si le plugin ne répond pas.
  }
}

export async function chargerHorloge() {
  const avant = Date.now();
  try {
    const h = await reveil.horloge();
    noterHorloge(h, avant, Date.now());
  } catch {
    // Sans horloge, le diagnostic montre ce qu'il a.
  }
}

export async function chargerDiagnostic() {
  const avant = Date.now();
  try {
    const d = await reveil.diagnostic();
    noterHorloge(d.horloge, avant, Date.now());
    etat.diagnostic = d;
    etat.erreurDiagnostic = null;
  } catch (e) {
    etat.erreurDiagnostic = e;
  }
}

// ── les noms de ce que jouent les alarmes ────────────────────────────────

let playlistsChargees = null;
let genresCharges = null;

export function chargerPlaylists() {
  playlistsChargees ??= coeur.playlists().then((l) => {
    for (const p of l) etat.refs.playlists[p.id] = p;
    return l;
  }).catch(() => { playlistsChargees = null; return []; });
  return playlistsChargees;
}

export function chargerGenres() {
  genresCharges ??= coeur.genres().then((l) => {
    for (const g of l) etat.refs.genres[g.id] = g;
    return l;
  }).catch(() => { genresCharges = null; return []; });
  return genresCharges;
}

function completerRefs(alarmes) {
  if (alarmes.some((a) => a.contexte === "playlist")) chargerPlaylists();
  if (alarmes.some((a) => a.genre_id)) chargerGenres();
  for (const a of alarmes) {
    if (a.contexte === "artiste" && a.contexte_id && !(a.contexte_id in etat.refs.artistes)) {
      etat.refs.artistes[a.contexte_id] = null;
      coeur.artiste(a.contexte_id).then((x) => { etat.refs.artistes[a.contexte_id] = { id: x.id, nom: nomArtiste(x) }; }).catch(() => {});
    }
    if (a.contexte === "album" && a.contexte_id && !(a.contexte_id in etat.refs.albums)) {
      etat.refs.albums[a.contexte_id] = null;
      coeur.album(a.contexte_id).then((x) => {
        etat.refs.albums[a.contexte_id] = { id: x.id, nom: nomAlbum(x), artiste: x.artist_name || "" };
      }).catch(() => {});
    }
  }
}

/** Ce que joue une alarme, en deux lignes : `[« Playlist … », « mélangée »]`. */
export function quoi(a) {
  const r = etat.refs;
  if (a.contexte === "playlist") {
    const p = r.playlists[a.contexte_id];
    return [`Playlist « ${p ? p.name : "…"} »`, a.melange ? "mélangée" : "dans l'ordre"];
  }
  if (a.contexte === "artiste") {
    const p = r.artistes[a.contexte_id];
    return [p ? `Tirage : ${p.nom}` : "Tirage : un artiste", "un artiste"];
  }
  if (a.contexte === "album") {
    const p = r.albums[a.contexte_id];
    return [p ? `Album « ${p.nom} »` : "Un album", p?.artiste || "tirage dans ses pistes"];
  }
  const g = a.genre_id ? r.genres[a.genre_id]?.name || "un genre" : "tous genres";
  const f = [g, a.format || "tous formats"];
  if (a.favoris) f.push("favoris");
  return ["Tirage dans la bibliothèque", f.join(" · ")];
}

// ── le testeur de fuseau ─────────────────────────────────────────────────

let sondeTest = null;

export async function lancerTest(dansS) {
  const avant = Date.now();
  const r = await reveil.tester(dansS);
  noterHorloge(r.horloge, avant, Date.now());
  const h = r.horloge;
  etat.test = {
    id: r.alarme.id,
    nom: r.alarme.nom,
    alarme: r.alarme,
    heure: heureDe(r.echeance),
    echeanceMs: Date.parse(r.echeance_utc) - (etat.decalageServeurMs || 0),
    etat: "en_attente",
    retardMs: null,
    resultat: null,
    trace: { serveur: heureDe(h.local), decalage: h.decalage, utc: heureDe(h.utc) },
    retraitMs: null,
    retiree: false,
  };
  await chargerAlarmes();
  suivreTest();
}

function suivreTest() {
  clearTimeout(sondeTest);
  const t = etat.test;
  if (!t) return;
  sondeTest = setTimeout(async () => {
    if (etat.test !== t) return;
    try {
      const r = await reveil.resultatTest(t.id);
      if (r.etat === "partie" || r.etat === "manquee") {
        const premier = t.etat !== r.etat;
        t.etat = r.etat;
        t.retardMs = r.retard_ms;
        t.resultat = r.dernier_resultat;
        if (premier) {
          t.retraitMs = Date.now() + GARDE_TEST_MS;
          chargerAlarmes();
          chargerSeance();
        }
      } else if (Date.now() > t.echeanceMs + ATTENTE_DEPART_MS && t.etat === "en_attente") {
        t.etat = "pas_partie";
        t.retraitMs = Date.now() + GARDE_TEST_MS;
      }
    } catch {
      // Une sonde ratée ne change rien : la suivante réessaie.
    }
    // On suit jusqu'au résultat de la séance (il arrive après le départ),
    // et tant que la ligne est montrée.
    const fini = t.etat !== "en_attente" && t.etat !== "pas_partie" && t.resultat;
    if (!fini && (!t.retraitMs || Date.now() < t.retraitMs)) suivreTest();
  }, 1000);
}

/** « mais ampli injoignable » : ce que le résultat de la séance ajoute à un
 *  départ à l'heure. Rien si elle a joué, ou si on ne le sait pas encore. */
export function suiteDuTest(t) {
  if (!t || !t.resultat || t.resultat === "joue" || t.resultat === "remplacee") return "";
  const muettes = ["adresse_reseau_non_reglee", "aucune_piste", "aucun_format_commun", "ampli_injoignable", "lecture_impossible"];
  const lib = resultat(t.resultat).lib.toLowerCase();
  return `mais ${lib}${muettes.includes(t.resultat) && t.resultat !== "ampli_injoignable" ? " : rien n'a joué" : ""}`;
}

export function retirerTest() {
  if (etat.test) etat.test.retiree = true;
}

/** La seconde qui passe : horloges, comptes à rebours, retrait de la ligne
 *  de test au bout de 60 s. */
export function battre() {
  etat.maintenant = Date.now();
  const t = etat.test;
  if (t && !t.retiree && t.retraitMs && Date.now() > t.retraitMs) t.retiree = true;
}
