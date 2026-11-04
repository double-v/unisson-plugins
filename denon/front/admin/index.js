const __hote$2 = globalThis.__unisson__.vue;
const __hote$1 = globalThis.__unisson__.vueRouter;
const hote = globalThis.__unisson__;
const deja = {};
const __hote = new Proxy({}, {
  get: (_, nom) => deja[nom] ?? (deja[nom] = hote.vue.defineAsyncComponent(() => hote.ds.charger().then((m) => m[nom])))
});
const _hoisted_1$6 = ["innerHTML"];
const _sfc_main$6 = {
  __name: "Icone",
  props: { nom: { type: String, required: true }, taille: { type: String, default: "1.15em" } },
  setup(__props) {
    const TRACES = {
      plus: '<path d="M12 5v14M5 12h14"/>',
      play: '<path d="M7 5v14l11-7z"/>',
      edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
      trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
      stop: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
      alert: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>',
      info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
      check: '<path d="M5 12.5 10 17l9-10"/>',
      back: '<path d="M15 6l-6 6 6 6"/>',
      spin: '<path d="M12 3a9 9 0 1 0 9 9"/>',
      clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
      link: '<path d="M10 14 21 3M15 3h6v6M19 14v6H4V5h6"/>',
      search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>'
    };
    return (_ctx, _cache) => {
      return __hote$2.openBlock(), __hote$2.createElementBlock("svg", {
        style: __hote$2.normalizeStyle({ width: __props.taille, height: __props.taille, flex: "0 0 auto" }),
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        "stroke-width": "1.8",
        "stroke-linecap": "round",
        "stroke-linejoin": "round",
        "aria-hidden": "true",
        innerHTML: TRACES[__props.nom] || ""
      }, null, 12, _hoisted_1$6);
    };
  }
};
const _hoisted_1$5 = ["role"];
const _hoisted_2$5 = { style: { "display": "flex", "flex-direction": "column", "gap": "var(--space-1)", "min-width": "0", "flex": "1" } };
const _sfc_main$5 = {
  __name: "Note",
  props: { ton: { type: String, default: "info" }, role: { type: String, default: "status" } },
  setup(__props) {
    const TONS = {
      info: { fond: "accent-soft", icone: "accent" },
      warning: { fond: "warning-soft", icone: "warning" },
      danger: { fond: "danger-soft", icone: "danger" }
    };
    return (_ctx, _cache) => {
      return __hote$2.openBlock(), __hote$2.createElementBlock("div", {
        role: __props.role,
        style: __hote$2.normalizeStyle({
          display: "flex",
          gap: "var(--space-2-5)",
          alignItems: "flex-start",
          padding: "var(--space-2-5) var(--space-3-5)",
          borderRadius: "var(--radius-md)",
          fontSize: "var(--text-sm)",
          background: `var(--color-${TONS[__props.ton].fond})`
        })
      }, [
        __hote$2.createElementVNode("span", {
          style: __hote$2.normalizeStyle({ color: `var(--color-${TONS[__props.ton].icone})`, marginTop: "2px", display: "inline-flex" })
        }, [
          __hote$2.createVNode(_sfc_main$6, {
            nom: __props.ton === "info" ? "info" : "alert"
          }, null, 8, ["nom"])
        ], 4),
        __hote$2.createElementVNode("div", _hoisted_2$5, [
          __hote$2.renderSlot(_ctx.$slots, "default")
        ]),
        __hote$2.renderSlot(_ctx.$slots, "actions")
      ], 12, _hoisted_1$5);
    };
  }
};
const { api } = globalThis.__unisson__;
const BASE = "/plugins/denon/reveil";
class ErreurReveil extends Error {
  constructor({ statut = 0, code = "", message = "", erreurs = [], reglage = null }) {
    super(message || code || "erreur");
    Object.assign(this, { statut, code, erreurs, reglage });
  }
}
const MESSAGES = {
  // Les routes du réveil exigent la même origine (garde du cœur ≥ 0.6) : une
  // page servie par un autre nom d'hôte que ceux d'unisson est refusée.
  403: "Requête refusée par unisson : cette page n'est pas servie sous une adresse qu'il reconnaît (même origine, DEDUP_ALLOWED_HOSTS) (403).",
  404: "Le plugin Denon ne répond pas : il est peut-être désactivé (404).",
  503: "Le plugin Denon ne répond pas (503)."
};
function normaliser(e) {
  const r = e == null ? void 0 : e.response;
  if (!r) return new ErreurReveil({ message: "Le serveur ne répond pas. Vérifiez qu'unisson tourne." });
  const d = r.data && typeof r.data === "object" ? r.data : {};
  const message = typeof d.message === "string" ? d.message : typeof d.detail === "string" ? d.detail : MESSAGES[r.status] || `Réponse inattendue du serveur (${r.status}).`;
  return new ErreurReveil({
    statut: r.status,
    code: d.error || "",
    // Le motif du cœur (`detail`) dit quelle origine ou quel hôte est refusé.
    message: r.status === 403 ? `${MESSAGES[403]}${typeof d.detail === "string" ? ` ${d.detail}` : ""}` : message,
    erreurs: Array.isArray(d.erreurs) ? d.erreurs : [],
    reglage: d.reglage || null
  });
}
const appel = (p) => p.catch((e) => {
  throw normaliser(e);
});
const reveil = {
  alarmes: () => appel(api.get(`${BASE}/alarmes`)),
  creer: (corps) => appel(api.post(`${BASE}/alarmes`, corps)),
  modifier: (id, corps) => appel(api.put(`${BASE}/alarmes/${id}`, corps)),
  supprimer: (id) => appel(api.delete(`${BASE}/alarmes/${id}`)),
  essayer: (id) => appel(api.post(`${BASE}/alarmes/${id}/essayer`)),
  tester: (dansS) => appel(api.post(`${BASE}/tester`, { dans_s: dansS })),
  resultatTest: (id) => appel(api.get(`${BASE}/tester/${id}`)),
  horloge: () => appel(api.get(`${BASE}/horloge`)),
  seance: () => appel(api.get(`${BASE}/seance`)),
  arreter: () => appel(api.post(`${BASE}/seance/arreter`)),
  diagnostic: () => appel(api.get(`${BASE}/diagnostic`)),
  regler: (valeurs) => appel(api.put("/plugins/denon/settings", valeurs))
};
const coeur = {
  playlists: () => appel(api.get("/playlists", { limit: 500 })).then((p) => p.items || []),
  genres: () => appel(api.get("/genres")),
  artistes: (q) => appel(api.get("/artists", { search: q, limit: 8, with_stats: true })).then((p) => p.items || []),
  artiste: (id) => appel(api.get(`/artists/${id}`)),
  albums: (q) => appel(api.get("/albums/search", { q })).then((l) => (l || []).slice(0, 8)),
  album: (id) => appel(api.get(`/albums/${id}`))
};
const nomArtiste = (a) => (a == null ? void 0 : a.display_name) || (a == null ? void 0 : a.name_from_nfo) || (a == null ? void 0 : a.folder_name) || (a == null ? void 0 : a.name) || "";
const nomAlbum = (a) => (a == null ? void 0 : a.name) || (a == null ? void 0 : a.name_from_nfo) || (a == null ? void 0 : a.name_from_tags) || (a == null ? void 0 : a.name_from_folder) || (a == null ? void 0 : a.folder_name) || "";
const JOURS = ["L", "M", "M", "J", "V", "S", "D"];
const JOURS_LONGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
const FORMATS = ["FLAC", "MP3", "M4A", "OGG", "WAV"];
const PRESETS_MONTEE = [0, 120, 300, 600, 900];
const FUSEAUX = ["Europe/Paris", "Europe/Brussels", "Europe/London", "UTC", "America/Montreal", "Indian/Reunion"];
const SEUIL_FORT_DB = -15;
const pad = (n) => String(n).padStart(2, "0");
function db(v) {
  if (v == null || Number.isNaN(+v)) return "—";
  const n = +v;
  const signe = n < 0 ? "−" : n > 0 ? "+" : "";
  return `${signe}${Math.abs(n).toFixed(1).replace(".", ",").replace(",0", "")} dB`;
}
function duree(s) {
  if (s === 0) return "d'emblée";
  if (s >= 3600) return "1 h";
  if (s < 60) return `${s} s`;
  return s % 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s / 60} min`;
}
function hm(heure) {
  if (!heure) return "—";
  const [h, ...reste] = heure.split(":");
  return [String(+h), ...reste].join(":");
}
function libJours(j) {
  if (j === 0) return "une seule fois";
  if (j === 127) return "tous les jours";
  if (j === 31) return "en semaine";
  if (j === 96) return "le week-end";
  return JOURS_LONGS.filter((_, i) => j & 1 << i).join(", ");
}
function fin(a) {
  if (a.fin_mode === "duree") return `${a.fin_valeur} min puis veille`;
  if (a.fin_mode === "pistes") return `${a.fin_valeur} piste${a.fin_valeur > 1 ? "s" : ""} puis veille`;
  return "sans limite";
}
function virgule(n, decimales = 1) {
  return Number(n).toFixed(decimales).replace(".", ",");
}
function parties(date, fuseau) {
  const o = {};
  new Intl.DateTimeFormat("en-GB", {
    timeZone: fuseau,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    weekday: "short"
  }).formatToParts(date).forEach((p) => {
    o[p.type] = p.value;
  });
  return o;
}
function murale(date, fuseau) {
  const o = parties(date, fuseau);
  return Date.UTC(+o.year, o.month - 1, +o.day, +o.hour, +o.minute, +o.second);
}
function hms(date, fuseau) {
  const o = parties(date, fuseau);
  return `${o.hour}:${o.minute}:${o.second}`;
}
function decalage(date, fuseau) {
  try {
    const n = new Intl.DateTimeFormat("en-US", { timeZone: fuseau, timeZoneName: "longOffset" }).formatToParts(date).find((p) => p.type === "timeZoneName").value;
    return n === "GMT" ? "+00:00" : n.replace("GMT", "");
  } catch {
    return "";
  }
}
const fuseauNavigateur = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
function libEcart(s) {
  const a = Math.abs(Math.round(s));
  if (a < 2) return "moins de 1 s";
  const h = Math.floor(a / 3600), m = Math.floor(a % 3600 / 60), r = a % 60;
  return [h && `${h} h`, m && `${m} min`, r && !h && `${r} s`].filter(Boolean).join(" ");
}
const ISO_LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/;
function lireLocal(iso) {
  const m = ISO_LOCAL.exec(iso || "");
  return m ? { a: +m[1], mo: +m[2], j: +m[3], h: +m[4], mi: +m[5], s: +m[6] } : null;
}
const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
function quand(iso, fuseau, maintenant = /* @__PURE__ */ new Date()) {
  const l = lireLocal(iso);
  if (!l) return "";
  const o = parties(maintenant, fuseau);
  const jour = Date.UTC(l.a, l.mo - 1, l.j);
  const auj = Date.UTC(+o.year, o.month - 1, +o.day);
  const ecartJours = Math.round((jour - auj) / 864e5);
  const heure = `${l.h}:${pad(l.mi)}${l.s ? `:${pad(l.s)}` : ""}`;
  if (ecartJours === 0) return `aujourd'hui ${heure}`;
  if (ecartJours === 1) return `demain ${heure}`;
  if (ecartJours === -1) return `hier ${heure}`;
  if (Math.abs(ecartJours) < 7) {
    const js = new Date(jour).getUTCDay();
    return `${JOURS_LONGS[(js + 6) % 7]} ${heure}`;
  }
  return `${l.j} ${MOIS[l.mo - 1]} ${heure}`;
}
function heureDe(iso) {
  const l = lireLocal(iso);
  return l ? `${pad(l.h)}:${pad(l.mi)}:${pad(l.s)}` : "";
}
function prochaineApercu(heure, jours, fuseau, maintenant = /* @__PURE__ */ new Date()) {
  const m = /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(heure || "");
  if (!m) return null;
  const [h, mi, s] = [+m[1], +m[2], +(m[3] || 0)];
  const ici = murale(maintenant, fuseau);
  const minuit = ici - ici % 864e5;
  for (let k = 0; k < 8; k++) {
    const t = minuit + k * 864e5 + ((h * 60 + mi) * 60 + s) * 1e3;
    if (t <= ici) continue;
    const js = new Date(t).getUTCDay();
    const bit = js === 0 ? 64 : 1 << js - 1;
    if (jours === 0 || jours & bit) {
      const lib = k === 0 ? "aujourd'hui" : k === 1 ? "demain" : JOURS_LONGS[(js + 6) % 7];
      return `${lib} ${h}:${pad(mi)}${s ? `:${pad(s)}` : ""}`;
    }
  }
  return null;
}
const RESULTATS = {
  joue: { ton: "success", lib: "Jouée" },
  arretee: { ton: "neutral", lib: "Arrêtée à la main" },
  remplacee: { ton: "neutral", lib: "Remplacée par une autre" },
  reprise_en_main: { ton: "neutral", lib: "Reprise en main" },
  pistes_epuisees: { ton: "neutral", lib: "Plus rien à jouer" },
  plugin_desactive: { ton: "neutral", lib: "Plugin désactivé" },
  interrompue: { ton: "neutral", lib: "Interrompue" },
  lien_mort: { ton: "danger", lib: "Lien telnet perdu" },
  ampli_injoignable: { ton: "danger", lib: "Ampli injoignable" },
  lecture_impossible: { ton: "danger", lib: "Lecture refusée par l'ampli" },
  adresse_reseau_non_reglee: { ton: "warning", lib: "Adresse réseau non réglée" },
  manquee: { ton: "warning", lib: "Manquée" },
  aucune_piste: { ton: "warning", lib: "Rien à jouer" },
  aucun_format_commun: { ton: "warning", lib: "Aucun format lisible" },
  contexte_inconnu: { ton: "warning", lib: "Contexte introuvable" },
  jamais: { ton: "neutral", lib: "Pas encore partie" }
};
function resultat(code) {
  if (!code) return RESULTATS.jamais;
  if (RESULTATS[code]) return RESULTATS[code];
  if (code.startsWith("erreur:")) return { ton: "danger", lib: "Erreur interne" };
  return { ton: "warning", lib: code.replaceAll("_", " ") };
}
const AIDE_RESULTAT = {
  ampli_injoignable: "L'ampli n'a pas répondu. Voir le diagnostic.",
  adresse_reseau_non_reglee: "L'ampli ne sait pas où chercher la musique : réglez l'adresse réseau d'unisson.",
  manquee: "unisson était arrêté à l'heure prévue, et a redémarré plus de 10 min après.",
  aucune_piste: "Le contexte choisi n'a aucune piste jouable.",
  aucun_format_commun: "Aucune piste n'est dans un format que l'ampli lit, même convertie.",
  lecture_impossible: "L'ampli s'est allumé, mais n'est pas passé en lecture."
};
function formatsCourts(protocoles) {
  const NOMS = {
    "audio/flac": "FLAC",
    "audio/x-flac": "FLAC",
    "audio/mpeg": "MP3",
    "audio/mp3": "MP3",
    "audio/x-mpeg": "MP3",
    "audio/mp4": "AAC",
    "audio/x-m4a": "AAC",
    "audio/aac": "AAC",
    "audio/x-aac": "AAC",
    "audio/m4a": "AAC",
    "audio/wav": "WAV",
    "audio/x-wav": "WAV",
    "audio/wave": "WAV",
    "audio/l16": "PCM",
    "audio/lpcm": "PCM",
    "audio/aiff": "AIFF",
    "audio/x-aiff": "AIFF",
    "audio/x-ms-wma": "WMA",
    "audio/wma": "WMA",
    "audio/ogg": "OGG",
    "audio/x-ogg": "OGG",
    "application/ogg": "OGG",
    "audio/x-alac": "ALAC",
    "audio/alac": "ALAC",
    "audio/dsd": "DSD",
    "audio/x-dsd": "DSD",
    "audio/x-dsf": "DSD",
    "audio/x-dff": "DSD"
  };
  const vus = [];
  for (const p of protocoles || []) {
    const mime = (String(p).split(":")[2] || "").split(";")[0].trim().toLowerCase();
    const nom = NOMS[mime] || (mime.startsWith("audio/") ? mime.slice(6).replace(/^x-/, "").toUpperCase() : null);
    if (nom && !vus.includes(nom)) vus.push(nom);
  }
  return vus;
}
const GARDE_TEST_MS = 6e4;
const ATTENTE_DEPART_MS = 1e4;
const etat = __hote$2.reactive({
  fuseau: "Europe/Paris",
  avertissementFuseau: null,
  alarmes: null,
  // null : pas encore chargées
  erreurListe: null,
  seance: null,
  derniere: null,
  diagnostic: null,
  erreurDiagnostic: null,
  // L'horloge : l'écart entre l'heure du serveur et celle de ce navigateur,
  // mesuré au dernier appel (corrigé de la moitié de l'aller-retour).
  decalageServeurMs: null,
  test: null,
  // { id, nom, heure, echeanceMs, etat, retardMs, resultat, trace, retraitMs }
  refs: { playlists: {}, artistes: {}, albums: {}, genres: {} },
  maintenant: Date.now()
});
const serveurMaintenant = () => new Date(Date.now() + (etat.decalageServeurMs || 0));
function noterHorloge(h, avantMs, apresMs) {
  if (!h) return;
  etat.fuseau = h.fuseau || etat.fuseau;
  etat.avertissementFuseau = h.avertissement || null;
  const utc = Date.parse(h.utc);
  if (!Number.isNaN(utc)) etat.decalageServeurMs = utc - (avantMs + apresMs) / 2;
}
async function chargerAlarmes() {
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
let seqSeance = 0;
let seanceEnVol = false;
let arretEnCours = false;
async function chargerSeance({ force = false } = {}) {
  if (arretEnCours || seanceEnVol && !force) return;
  const n = ++seqSeance;
  seanceEnVol = true;
  try {
    const r = await reveil.seance();
    if (n !== seqSeance || arretEnCours) return;
    etat.seance = r.seance;
    etat.derniere = r.derniere;
  } catch {
  } finally {
    if (n === seqSeance) seanceEnVol = false;
  }
}
async function arreterSeance() {
  arretEnCours = true;
  seqSeance += 1;
  seanceEnVol = false;
  try {
    const r = await reveil.arreter();
    etat.seance = r.seance;
    etat.derniere = r.derniere;
  } finally {
    arretEnCours = false;
  }
}
async function chargerDiagnostic() {
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
let playlistsChargees = null;
let genresCharges = null;
function chargerPlaylists({ frais = false } = {}) {
  if (frais) playlistsChargees = null;
  playlistsChargees ?? (playlistsChargees = coeur.playlists().then((l) => {
    for (const p of l) etat.refs.playlists[p.id] = p;
    return l;
  }).catch(() => {
    playlistsChargees = null;
    return [];
  }));
  return playlistsChargees;
}
function chargerGenres({ frais = false } = {}) {
  if (frais) genresCharges = null;
  genresCharges ?? (genresCharges = coeur.genres().then((l) => {
    for (const g of l) etat.refs.genres[g.id] = g;
    return l;
  }).catch(() => {
    genresCharges = null;
    return [];
  }));
  return genresCharges;
}
function completerRefs(alarmes) {
  if (alarmes.some((a) => a.contexte === "playlist")) chargerPlaylists();
  if (alarmes.some((a) => a.genre_id)) chargerGenres();
  for (const a of alarmes) {
    if (a.contexte === "artiste" && a.contexte_id && !(a.contexte_id in etat.refs.artistes)) {
      etat.refs.artistes[a.contexte_id] = null;
      coeur.artiste(a.contexte_id).then((x) => {
        etat.refs.artistes[a.contexte_id] = { id: x.id, nom: nomArtiste(x) };
      }).catch(() => {
      });
    }
    if (a.contexte === "album" && a.contexte_id && !(a.contexte_id in etat.refs.albums)) {
      etat.refs.albums[a.contexte_id] = null;
      coeur.album(a.contexte_id).then((x) => {
        etat.refs.albums[a.contexte_id] = { id: x.id, nom: nomAlbum(x), artiste: x.artist_name || "" };
      }).catch(() => {
      });
    }
  }
}
function quoi(a) {
  var _a;
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
    return [p ? `Album « ${p.nom} »` : "Un album", (p == null ? void 0 : p.artiste) || "tirage dans ses pistes"];
  }
  const g = a.genre_id ? ((_a = r.genres[a.genre_id]) == null ? void 0 : _a.name) || "un genre" : "tous genres";
  const f = [g, a.format || "tous formats"];
  if (a.favoris) f.push("favoris");
  return ["Tirage dans la bibliothèque", f.join(" · ")];
}
let sondeTest = null;
async function lancerTest(dansS) {
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
    retiree: false
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
    }
    if (!testFini(t) && Date.now() < t.echeanceMs + SUIVI_MAX_MS) suivreTest();
  }, 1e3);
}
const SUIVI_MAX_MS = 5 * 6e4;
const sansResultat = (t) => !t.resultat || t.resultat === "en_cours";
const testFini = (t) => (t.etat === "partie" || t.etat === "manquee") && !sansResultat(t);
function reprendreSuiviTest() {
  const t = etat.test;
  if (t && !testFini(t) && Date.now() < t.echeanceMs + SUIVI_MAX_MS) suivreTest();
}
function arreterSuiviTest() {
  clearTimeout(sondeTest);
  sondeTest = null;
}
function suiteDuTest(t) {
  if (!t || sansResultat(t) || t.resultat === "joue" || t.resultat === "remplacee") return "";
  const muettes = ["adresse_reseau_non_reglee", "aucune_piste", "aucun_format_commun", "ampli_injoignable", "lecture_impossible"];
  const lib = resultat(t.resultat).lib.toLowerCase();
  return `mais ${lib}${muettes.includes(t.resultat) && t.resultat !== "ampli_injoignable" ? " : rien n'a joué" : ""}`;
}
function retirerTest() {
  if (etat.test) etat.test.retiree = true;
}
function battre() {
  etat.maintenant = Date.now();
  const t = etat.test;
  if (t && !t.retiree && t.retraitMs && Date.now() > t.retraitMs) t.retiree = true;
}
const _hoisted_1$4 = {
  key: 2,
  "data-test": "denon-diagnostic",
  style: { "display": "flex", "flex-direction": "column", "gap": "var(--space-6)" }
};
const _hoisted_2$4 = { style: { "font-family": "var(--font-mono)" } };
const _hoisted_3$4 = { style: { "margin": "calc(-1 * var(--space-1)) calc(-1 * var(--space-4)) calc(-1 * var(--space-4))" } };
const _hoisted_4$4 = { style: { "font-family": "var(--font-mono)" } };
const _hoisted_5$4 = { style: { "font-family": "var(--font-mono)" } };
const _hoisted_6$4 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-1)" } };
const _hoisted_7$3 = {
  key: 1,
  style: { "color": "var(--color-ink-faint)" }
};
const _hoisted_8$3 = { style: { "display": "flex", "flex-direction": "column", "gap": "var(--space-4)" } };
const _hoisted_9$3 = { style: { "display": "flex", "flex-direction": "column", "gap": "var(--space-1-5)", "max-width": "18rem" } };
const _hoisted_10$3 = ["value"];
const _hoisted_11$2 = { style: { "font-size": "11px", "font-weight": "600", "letter-spacing": ".04em", "color": "var(--color-ink-muted)" } };
const _hoisted_12$2 = { style: { "font-family": "var(--font-mono)", "font-variant-numeric": "tabular-nums", "font-size": "var(--text-xl)", "font-weight": "500", "letter-spacing": "-0.02em" } };
const _hoisted_13$2 = { style: { "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)", "font-family": "var(--font-mono)" } };
const _hoisted_14$2 = {
  key: 1,
  style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-2)", "align-items": "center" }
};
const _hoisted_15$2 = { style: { "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)" } };
const _hoisted_16$2 = { style: { "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)" } };
const _hoisted_17$1 = { style: { "display": "flex", "flex-direction": "column", "gap": "var(--space-2-5)" } };
const _hoisted_18$1 = { style: { "margin": "0", "max-width": "62ch", "color": "var(--color-ink-muted)" } };
const _hoisted_19$1 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-2)", "align-items": "center" } };
const _hoisted_20$1 = {
  key: 1,
  "aria-live": "polite",
  style: { "display": "flex", "flex-direction": "column", "gap": "var(--space-2)" }
};
const _hoisted_21$1 = { style: { "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)" } };
const _hoisted_22$1 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-2)", "align-items": "center" } };
const _hoisted_23$1 = { style: { "font-family": "var(--font-mono)", "font-size": "12px", "color": "var(--color-ink-muted)", "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-1) var(--space-4)" } };
const _hoisted_24$1 = { style: { "margin": "0", "padding": "0", "list-style": "none", "display": "flex", "flex-direction": "column", "gap": "var(--space-3)" } };
const _hoisted_25$1 = { style: { "margin-top": "3px", "color": "var(--color-accent)", "display": "inline-flex" } };
const _hoisted_26$1 = {
  key: 0,
  style: { "font-weight": "600" }
};
const _hoisted_27$1 = { style: { "color": "var(--color-ink-faint)" } };
const _hoisted_28$1 = { style: { "font-family": "var(--font-mono)" } };
const _sfc_main$4 = {
  __name: "Diagnostic",
  props: { etroit: Boolean },
  setup(__props) {
    const props = __props;
    const d = __hote$2.computed(() => etat.diagnostic);
    const t = __hote$2.computed(() => etat.test);
    const charge = __hote$2.ref(false);
    const reglage = __hote$2.ref(false);
    const erreurReglage = __hote$2.ref("");
    const erreurTest = __hote$2.ref("");
    const lancement = __hote$2.ref(null);
    const navTz = fuseauNavigateur();
    const TITRES = {
      controle_reseau: "Garder le contrôle réseau en veille.",
      ip_fixe: "Donner une IP fixe à l'ampli."
    };
    async function relancer() {
      charge.value = true;
      await chargerDiagnostic();
      charge.value = false;
    }
    const formats = __hote$2.computed(() => {
      var _a, _b;
      return formatsCourts((_b = (_a = d.value) == null ? void 0 : _a.upnp) == null ? void 0 : _b.formats);
    });
    const plafond = __hote$2.computed(() => {
      var _a, _b;
      const p = (_b = (_a = d.value) == null ? void 0 : _a.pilote) == null ? void 0 : _b.plafond;
      if (!p) return "";
      const bits = p.profondeur_max ? `${p.profondeur_max} bits` : "";
      const khz = p.frequence_max ? `${virgule(p.frequence_max / 1e3, p.frequence_max % 1e3 ? 1 : 0)} kHz` : "";
      return ` Plafond du pilote : ${[bits, khz].filter(Boolean).join(" / ")} ; au-delà, unisson convertit.`;
    });
    const etatAmpli = __hote$2.computed(() => {
      const tl = d.value.telnet;
      const parts = [];
      if (tl.alimentation === true) parts.push("allumé");
      else if (tl.alimentation === false) parts.push("en veille");
      if (tl.source) parts.push(`source ${tl.source}`);
      if (tl.volume != null) parts.push(db(tl.volume));
      return parts.length ? ` · ${parts.join(" · ")}` : "";
    });
    const fuseaux = __hote$2.computed(() => FUSEAUX.includes(etat.fuseau) ? FUSEAUX : [etat.fuseau, ...FUSEAUX]);
    const horloges = __hote$2.computed(() => {
      void etat.maintenant;
      const sn = serveurMaintenant(), nav = /* @__PURE__ */ new Date();
      return [
        { lib: `Serveur, ${etat.fuseau}`, h: hms(sn, etat.fuseau), s: decalage(sn, etat.fuseau) },
        { lib: "Serveur, UTC", h: hms(sn, "UTC"), s: "+00:00" },
        { lib: "Ce navigateur", h: hms(nav, navTz), s: `${navTz} ${decalage(nav, navTz)}` }
      ];
    });
    const ecart = __hote$2.computed(() => {
      void etat.maintenant;
      if (etat.decalageServeurMs == null) return 0;
      return (murale(serveurMaintenant(), etat.fuseau) - murale(/* @__PURE__ */ new Date(), navTz)) / 1e3;
    });
    const alerteEcart = __hote$2.computed(() => Math.abs(ecart.value) > 60);
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
    const modele = __hote$2.computed(() => {
      const l = (etat.alarmes || []).filter((a) => !a.test);
      return l.length ? l.reduce((a, b) => a.id < b.id ? a : b) : null;
    });
    const descriptionTest = __hote$2.computed(() => modele.value ? `Crée une alarme unique qui part par l'ordonnanceur, comme une vraie, avec ce que joue « ${modele.value.nom} » et ses volumes, fin après 1 piste. Elle se retire seule après son passage.` : "Crée une alarme unique qui part par l'ordonnanceur, comme une vraie : un tirage de la bibliothèque à −50 dB, fin après 1 piste. Elle se retire seule après son passage.");
    const testEnAttente = __hote$2.computed(() => {
      var _a;
      return ((_a = t.value) == null ? void 0 : _a.etat) === "en_attente";
    });
    const reste = __hote$2.computed(() => Math.max(0, Math.ceil((t.value.echeanceMs - etat.maintenant) / 1e3)));
    const suite = __hote$2.computed(() => suiteDuTest(t.value));
    async function tester(n) {
      var _a;
      lancement.value = n;
      erreurTest.value = "";
      try {
        await lancerTest(n);
      } catch (e) {
        erreurTest.value = ((_a = e.erreurs) == null ? void 0 : _a.length) ? e.erreurs.map((x) => x.message).join(" ; ") : e.message;
      } finally {
        lancement.value = null;
      }
    }
    const ligne = (i) => ({
      display: "grid",
      gridTemplateColumns: props.etroit ? "1fr" : "11rem minmax(0, 1fr)",
      gap: "var(--space-2) var(--space-4)",
      padding: "var(--space-3) var(--space-4)",
      alignItems: "start",
      borderTop: i ? "1px solid var(--color-border)" : void 0
    });
    const nomStyle = { fontWeight: 600, display: "flex", alignItems: "center", gap: "var(--space-2)" };
    const valStyle = { display: "flex", flexDirection: "column", gap: "var(--space-1-5)", alignItems: "flex-start", minWidth: 0 };
    const point = (ton) => ({ width: "8px", height: "8px", borderRadius: "50%", flex: "0 0 auto", background: `var(--color-${ton})` });
    const trace = { fontFamily: "var(--font-mono)", fontSize: "var(--text-xs)", color: "var(--color-ink-faint)", overflowWrap: "anywhere" };
    const muet = { color: "var(--color-ink-muted)" };
    const sousTitre = { margin: 0, color: "var(--color-ink-muted)", fontSize: "var(--text-sm)" };
    const indice = { fontSize: "var(--text-xs)", color: "var(--color-ink-faint)" };
    const horloge = {
      padding: "var(--space-3)",
      background: "var(--color-surface-sunken)",
      borderRadius: "var(--radius-md)",
      display: "flex",
      flexDirection: "column",
      gap: "2px"
    };
    return (_ctx, _cache) => {
      return !d.value && !__hote$2.unref(etat).erreurDiagnostic ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiSkeleton), {
        key: 0,
        rows: 3,
        cols: 1
      })) : !d.value ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiErrorState), {
        key: 1,
        message: `Le diagnostic n'a pas pu être lu : ${__hote$2.unref(etat).erreurDiagnostic.message}`,
        "retry-label": "Réessayer",
        onRetry: relancer
      }, null, 8, ["message"])) : (__hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_1$4, [
        __hote$2.createVNode(__hote$2.unref(__hote.UiPanel), {
          title: "L'ampli",
          "title-tag": "h3",
          padding: "md"
        }, {
          header: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("p", { style: sousTitre }, [
              __hote$2.createTextVNode(__hote$2.toDisplayString(d.value.pilote.libelle) + " · ", 1),
              __hote$2.createElementVNode("span", _hoisted_2$4, __hote$2.toDisplayString(d.value.telnet.hote || "hôte non réglé"), 1)
            ])
          ]),
          actions: __hote$2.withCtx(() => [
            __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
              intent: "secondary",
              size: "sm",
              loading: charge.value,
              onClick: relancer
            }, {
              default: __hote$2.withCtx(() => [..._cache[0] || (_cache[0] = [
                __hote$2.createTextVNode("Relancer le diagnostic", -1)
              ])]),
              _: 1
            }, 8, ["loading"])
          ]),
          default: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("div", _hoisted_3$4, [
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(ligne(0))
              }, [
                __hote$2.createElementVNode("div", { style: nomStyle }, [
                  __hote$2.createElementVNode("span", {
                    style: __hote$2.normalizeStyle(point(d.value.telnet.connecte ? "success" : "danger"))
                  }, null, 4),
                  _cache[1] || (_cache[1] = __hote$2.createTextVNode("Telnet", -1))
                ]),
                __hote$2.createElementVNode("div", { style: valStyle }, [
                  d.value.telnet.connecte ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "success",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [..._cache[2] || (_cache[2] = [
                        __hote$2.createTextVNode("Connecté", -1)
                      ])]),
                      _: 1
                    }),
                    __hote$2.createElementVNode("span", { style: trace }, __hote$2.toDisplayString(d.value.telnet.hote) + ":" + __hote$2.toDisplayString(d.value.telnet.port) + __hote$2.toDisplayString(etatAmpli.value), 1)
                  ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "danger",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [..._cache[3] || (_cache[3] = [
                        __hote$2.createTextVNode("Déconnecté", -1)
                      ])]),
                      _: 1
                    }),
                    !d.value.telnet.hote ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 0,
                      style: muet
                    }, "Aucun hôte réglé : renseignez l'adresse IP de l'ampli dans les réglages du plugin (Plugins › Denon).")) : (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 1,
                      style: muet
                    }, [
                      _cache[4] || (_cache[4] = __hote$2.createTextVNode("Pas de réponse de ", -1)),
                      __hote$2.createElementVNode("span", _hoisted_4$4, __hote$2.toDisplayString(d.value.telnet.hote) + ":" + __hote$2.toDisplayString(d.value.telnet.port), 1),
                      _cache[5] || (_cache[5] = __hote$2.createTextVNode(". L'ampli est peut-être en veille profonde : voir le premier conseil.", -1))
                    ]))
                  ], 64))
                ])
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(ligne(1))
              }, [
                __hote$2.createElementVNode("div", { style: nomStyle }, [
                  __hote$2.createElementVNode("span", {
                    style: __hote$2.normalizeStyle(point(d.value.upnp.joignable ? "success" : "danger"))
                  }, null, 4),
                  _cache[6] || (_cache[6] = __hote$2.createTextVNode("Lecteur UPnP", -1))
                ]),
                __hote$2.createElementVNode("div", { style: valStyle }, [
                  d.value.upnp.joignable ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "success",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [..._cache[7] || (_cache[7] = [
                        __hote$2.createTextVNode("Joignable", -1)
                      ])]),
                      _: 1
                    }),
                    __hote$2.createElementVNode("span", { style: trace }, __hote$2.toDisplayString(d.value.upnp.description), 1)
                  ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "danger",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [..._cache[8] || (_cache[8] = [
                        __hote$2.createTextVNode("Muet", -1)
                      ])]),
                      _: 1
                    }),
                    d.value.upnp.description ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 0,
                      style: muet
                    }, [
                      _cache[9] || (_cache[9] = __hote$2.createTextVNode("Aucune réponse sur ", -1)),
                      __hote$2.createElementVNode("span", _hoisted_5$4, __hote$2.toDisplayString(d.value.upnp.description), 1),
                      _cache[10] || (_cache[10] = __hote$2.createTextVNode(".", -1))
                    ])) : (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 1,
                      style: muet
                    }, "Aucune adresse : le lecteur se cherche sur l'hôte de l'ampli, port 8080.")),
                    d.value.upnp.erreur ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 2,
                      style: trace
                    }, __hote$2.toDisplayString(d.value.upnp.erreur), 1)) : __hote$2.createCommentVNode("", true)
                  ], 64))
                ])
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(ligne(2))
              }, [
                __hote$2.createElementVNode("div", { style: nomStyle }, [
                  __hote$2.createElementVNode("span", {
                    style: __hote$2.normalizeStyle(point(d.value.adresse_reseau.reglee ? "success" : "warning"))
                  }, null, 4),
                  _cache[11] || (_cache[11] = __hote$2.createTextVNode("Adresse d'unisson", -1))
                ]),
                __hote$2.createElementVNode("div", { style: valStyle }, [
                  d.value.adresse_reseau.reglee ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "success",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [..._cache[12] || (_cache[12] = [
                        __hote$2.createTextVNode("Réglée", -1)
                      ])]),
                      _: 1
                    }),
                    __hote$2.createElementVNode("span", { style: trace }, __hote$2.toDisplayString(d.value.adresse_reseau.adresse), 1)
                  ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "warning",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [..._cache[13] || (_cache[13] = [
                        __hote$2.createTextVNode("Non réglée", -1)
                      ])]),
                      _: 1
                    }),
                    __hote$2.createElementVNode("span", { style: muet }, "L'ampli va chercher la musique lui-même : il lui faut l'adresse d'unisson sur le réseau local."),
                    __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                      intent: "secondary",
                      size: "sm",
                      to: d.value.adresse_reseau.reglage.replace(/^\/admin/, "")
                    }, {
                      leading: __hote$2.withCtx(() => [
                        __hote$2.createVNode(_sfc_main$6, { nom: "link" })
                      ]),
                      default: __hote$2.withCtx(() => [
                        _cache[14] || (_cache[14] = __hote$2.createTextVNode("Régler dans Réglages › Réseau ", -1))
                      ]),
                      _: 1
                    }, 8, ["to"])
                  ], 64))
                ])
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(ligne(3))
              }, [
                __hote$2.createElementVNode("div", { style: nomStyle }, [
                  __hote$2.createElementVNode("span", {
                    style: __hote$2.normalizeStyle(point(formats.value.length ? "success" : "warning"))
                  }, null, 4),
                  _cache[15] || (_cache[15] = __hote$2.createTextVNode("Formats", -1))
                ]),
                __hote$2.createElementVNode("div", { style: valStyle }, [
                  formats.value.length ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                    __hote$2.createElementVNode("div", _hoisted_6$4, [
                      (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(formats.value, (f) => {
                        return __hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiChip), {
                          key: f,
                          tone: "neutral"
                        }, {
                          default: __hote$2.withCtx(() => [
                            __hote$2.createTextVNode(__hote$2.toDisplayString(f), 1)
                          ]),
                          _: 2
                        }, 1024);
                      }), 128))
                    ]),
                    __hote$2.createElementVNode("span", {
                      style: __hote$2.normalizeStyle({ ...muet, color: "var(--color-ink-faint)", fontSize: "var(--text-xs)" })
                    }, [
                      _cache[16] || (_cache[16] = __hote$2.createTextVNode("Annoncés par ", -1)),
                      _cache[17] || (_cache[17] = __hote$2.createElementVNode("span", { style: { "font-family": "var(--font-mono)" } }, "GetProtocolInfo", -1)),
                      __hote$2.createTextVNode("." + __hote$2.toDisplayString(plafond.value), 1)
                    ], 4)
                  ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_7$3, "Inconnus tant que le lecteur UPnP ne répond pas."))
                ])
              ], 4)
            ])
          ]),
          _: 1
        }),
        __hote$2.createVNode(__hote$2.unref(__hote.UiPanel), {
          title: "L'heure",
          "title-tag": "h3",
          padding: "md"
        }, {
          header: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("p", { style: sousTitre }, "Les alarmes suivent l'heure du serveur, dans le fuseau réglé.")
          ]),
          default: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("div", _hoisted_8$3, [
              __hote$2.createElementVNode("div", _hoisted_9$3, [
                __hote$2.createVNode(__hote$2.unref(__hote.UiSelect), {
                  "model-value": __hote$2.unref(etat).fuseau,
                  label: "Fuseau",
                  disabled: reglage.value,
                  block: "",
                  "onUpdate:modelValue": changerFuseau
                }, {
                  default: __hote$2.withCtx(() => [
                    (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(fuseaux.value, (f) => {
                      return __hote$2.openBlock(), __hote$2.createElementBlock("option", {
                        key: f,
                        value: f
                      }, __hote$2.toDisplayString(f === "Europe/Paris" ? "Europe/Paris (par défaut)" : f), 9, _hoisted_10$3);
                    }), 128))
                  ]),
                  _: 1
                }, 8, ["model-value", "disabled"]),
                erreurReglage.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                  key: 0,
                  style: __hote$2.normalizeStyle({ ...indice, color: "var(--color-danger)" })
                }, __hote$2.toDisplayString(erreurReglage.value), 5)) : (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                  key: 1,
                  style: indice
                }, "Réglage du plugin, utilisé pour toutes les alarmes."))
              ]),
              __hote$2.unref(etat).avertissementFuseau ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
                key: 0,
                ton: "warning",
                role: "alert"
              }, {
                default: __hote$2.withCtx(() => [
                  __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(__hote$2.unref(etat).avertissementFuseau), 1)
                ]),
                _: 1
              })) : __hote$2.createCommentVNode("", true),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle({ display: "grid", gridTemplateColumns: __props.etroit ? "1fr" : "repeat(3, minmax(0, 1fr))", gap: "var(--space-3)" })
              }, [
                (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(horloges.value, (h) => {
                  return __hote$2.openBlock(), __hote$2.createElementBlock("div", {
                    key: h.lib,
                    style: horloge
                  }, [
                    __hote$2.createElementVNode("span", _hoisted_11$2, __hote$2.toDisplayString(h.lib), 1),
                    __hote$2.createElementVNode("span", _hoisted_12$2, __hote$2.toDisplayString(h.h), 1),
                    __hote$2.createElementVNode("span", _hoisted_13$2, __hote$2.toDisplayString(h.s), 1)
                  ]);
                }), 128))
              ], 4),
              !alerteEcart.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_14$2, [
                __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                  tone: "success",
                  dot: ""
                }, {
                  default: __hote$2.withCtx(() => [
                    __hote$2.createTextVNode("Écart : " + __hote$2.toDisplayString(__hote$2.unref(libEcart)(ecart.value)), 1)
                  ]),
                  _: 1
                }),
                __hote$2.createElementVNode("span", _hoisted_15$2, "Comparé à l'heure de ce navigateur (" + __hote$2.toDisplayString(__hote$2.unref(navTz)) + ").", 1)
              ])) : (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
                key: 2,
                ton: "warning",
                role: "alert"
              }, {
                default: __hote$2.withCtx(() => [
                  _cache[18] || (_cache[18] = __hote$2.createElementVNode("b", null, "L'horloge ou le fuseau du serveur ne correspond pas.", -1)),
                  __hote$2.createElementVNode("span", null, "Le serveur est " + __hote$2.toDisplayString(ecart.value > 0 ? "en avance" : "en retard") + " de " + __hote$2.toDisplayString(__hote$2.unref(libEcart)(ecart.value)) + " sur ce navigateur. Les alarmes partiront à l'heure du serveur. Vérifiez le fuseau, ou la synchronisation NTP de la machine.", 1),
                  __hote$2.createElementVNode("span", _hoisted_16$2, "Comparé à l'heure de ce navigateur (" + __hote$2.toDisplayString(__hote$2.unref(navTz)) + ").", 1)
                ]),
                _: 1
              })),
              __hote$2.createElementVNode("div", _hoisted_17$1, [
                _cache[20] || (_cache[20] = __hote$2.createElementVNode("h4", { style: { "font-family": "var(--font-sans)", "line-height": "var(--text-xs-lh)", "font-size": "var(--text-xs)", "font-weight": "600", "letter-spacing": ".12em", "text-transform": "uppercase", "color": "var(--color-ink-muted)", "margin": "0" } }, "Tester le fuseau", -1)),
                __hote$2.createElementVNode("p", _hoisted_18$1, __hote$2.toDisplayString(descriptionTest.value), 1),
                __hote$2.createElementVNode("div", _hoisted_19$1, [
                  (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList([5, 10], (n) => {
                    return __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                      key: n,
                      intent: "secondary",
                      size: "md",
                      disabled: testEnAttente.value,
                      loading: lancement.value === n,
                      onClick: ($event) => tester(n)
                    }, {
                      leading: __hote$2.withCtx(() => [
                        __hote$2.createVNode(_sfc_main$6, { nom: "clock" })
                      ]),
                      default: __hote$2.withCtx(() => [
                        __hote$2.createTextVNode("Tester dans " + __hote$2.toDisplayString(n) + " s ", 1)
                      ]),
                      _: 2
                    }, 1032, ["disabled", "loading", "onClick"]);
                  }), 64))
                ]),
                erreurTest.value ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
                  key: 0,
                  ton: "danger",
                  role: "alert"
                }, {
                  default: __hote$2.withCtx(() => [
                    __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(erreurTest.value), 1)
                  ]),
                  _: 1
                })) : __hote$2.createCommentVNode("", true),
                t.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_20$1, [
                  __hote$2.createElementVNode("span", _hoisted_21$1, "Dernier test" + __hote$2.toDisplayString(t.value.etat !== "en_attente" && t.value.retiree ? " (ligne retirée de la liste, le résultat reste ici jusqu'au test suivant)" : ""), 1),
                  __hote$2.createElementVNode("div", _hoisted_22$1, [
                    t.value.etat === "en_attente" ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiChip), {
                      key: 0,
                      tone: "accent",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [
                        __hote$2.createTextVNode(__hote$2.toDisplayString(reste.value ? `part dans ${reste.value} s` : "échéance passée, on attend…"), 1)
                      ]),
                      _: 1
                    })) : t.value.etat === "partie" ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiChip), {
                      key: 1,
                      tone: "success",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [
                        __hote$2.createTextVNode("partie à " + __hote$2.toDisplayString(t.value.heure) + ", avec " + __hote$2.toDisplayString(__hote$2.unref(virgule)((t.value.retardMs || 0) / 1e3)) + " s de retard", 1)
                      ]),
                      _: 1
                    })) : (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiChip), {
                      key: 2,
                      tone: "danger",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [
                        __hote$2.createTextVNode("pas partie : attendue à " + __hote$2.toDisplayString(t.value.heure), 1)
                      ]),
                      _: 1
                    })),
                    t.value.etat === "partie" ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 3,
                      style: muet
                    }, __hote$2.toDisplayString(suite.value ? `L'heure est bonne, ${suite.value}.` : !t.value.resultat || t.value.resultat === "en_cours" ? "L'heure est bonne ; la séance joue encore." : "Le fuseau et l'horloge sont bons."), 1)) : __hote$2.createCommentVNode("", true)
                  ]),
                  __hote$2.createElementVNode("div", _hoisted_23$1, [
                    __hote$2.createElementVNode("span", null, "créée « " + __hote$2.toDisplayString(t.value.nom) + " »", 1),
                    __hote$2.createElementVNode("span", null, "serveur " + __hote$2.toDisplayString(t.value.trace.serveur) + " " + __hote$2.toDisplayString(t.value.trace.decalage), 1),
                    __hote$2.createElementVNode("span", null, "UTC " + __hote$2.toDisplayString(t.value.trace.utc), 1),
                    __hote$2.createElementVNode("span", null, "échéance " + __hote$2.toDisplayString(t.value.heure), 1)
                  ]),
                  t.value.etat === "pas_partie" || t.value.etat === "manquee" ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
                    key: 0,
                    ton: "danger"
                  }, {
                    default: __hote$2.withCtx(() => [..._cache[19] || (_cache[19] = [
                      __hote$2.createElementVNode("span", null, [
                        __hote$2.createTextVNode("L'ordonnanceur n'a pas déclenché l'alarme. Vérifiez le fuseau ci-dessus, puis les journaux "),
                        __hote$2.createElementVNode("span", { style: { "font-family": "var(--font-mono)" } }, "unisson.plugin.denon"),
                        __hote$2.createTextVNode(".")
                      ], -1)
                    ])]),
                    _: 1
                  })) : __hote$2.createCommentVNode("", true)
                ])) : __hote$2.createCommentVNode("", true)
              ])
            ])
          ]),
          _: 1
        }),
        __hote$2.createVNode(__hote$2.unref(__hote.UiPanel), {
          title: "Réglages de l'ampli",
          "title-tag": "h3",
          padding: "md"
        }, {
          header: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("p", { style: sousTitre }, "À faire une fois, sur l'ampli et sur la box.")
          ]),
          default: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("ul", _hoisted_24$1, [
              (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(d.value.conseils, (c) => {
                return __hote$2.openBlock(), __hote$2.createElementBlock("li", {
                  key: c.code,
                  style: { "display": "flex", "gap": "var(--space-3)", "align-items": "flex-start" }
                }, [
                  __hote$2.createElementVNode("span", _hoisted_25$1, [
                    __hote$2.createVNode(_sfc_main$6, { nom: "info" })
                  ]),
                  __hote$2.createElementVNode("div", null, [
                    TITRES[c.code] ? (__hote$2.openBlock(), __hote$2.createElementBlock("b", _hoisted_26$1, __hote$2.toDisplayString(TITRES[c.code]), 1)) : __hote$2.createCommentVNode("", true),
                    __hote$2.createTextVNode(" " + __hote$2.toDisplayString(c.message) + " ", 1),
                    c.code === "ip_fixe" && d.value.telnet.hote ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                      _cache[22] || (_cache[22] = __hote$2.createElementVNode("br", null, null, -1)),
                      __hote$2.createElementVNode("span", _hoisted_27$1, [
                        _cache[21] || (_cache[21] = __hote$2.createTextVNode("Adresse actuelle : ", -1)),
                        __hote$2.createElementVNode("span", _hoisted_28$1, __hote$2.toDisplayString(d.value.telnet.hote), 1)
                      ])
                    ], 64)) : __hote$2.createCommentVNode("", true)
                  ])
                ]);
              }), 128))
            ])
          ]),
          _: 1
        })
      ]));
    };
  }
};
const _hoisted_1$3 = { "data-test": "denon-formulaire" };
const _hoisted_2$3 = { style: { "margin-bottom": "var(--space-6)" } };
const _hoisted_3$3 = { style: { "display": "inline-block", "margin-left": "calc(-1 * var(--space-3))" } };
const _hoisted_4$3 = { style: { "display": "flex", "flex-direction": "column" } };
const _hoisted_5$3 = { style: { "display": "flex", "flex-direction": "column", "gap": "var(--space-1-5)" } };
const _hoisted_6$3 = {
  role: "group",
  "aria-label": "Jours",
  style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-1-5)", "align-items": "center" }
};
const _hoisted_7$2 = { style: { "color": "var(--color-ink)" } };
const _hoisted_8$2 = { style: { "display": "flex", "align-items": "center", "gap": "var(--space-3)" } };
const _hoisted_9$2 = ["aria-checked", "onClick"];
const _hoisted_10$2 = { style: { "font-weight": "600", "font-size": "var(--text-sm)" } };
const _hoisted_11$1 = { style: { "padding": "var(--space-4)", "background": "var(--color-surface-sunken)", "border-radius": "var(--radius-md)", "display": "flex", "flex-direction": "column", "gap": "var(--space-4)" } };
const _hoisted_12$1 = { value: "" };
const _hoisted_13$1 = ["value"];
const _hoisted_14$1 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-1-5)", "align-items": "center" } };
const _hoisted_15$1 = ["value"];
const _hoisted_16$1 = ["value"];
const _hoisted_17 = { style: { "display": "flex", "align-items": "center", "gap": "var(--space-3)", "min-height": "var(--space-9)" } };
const _hoisted_18 = ["aria-label"];
const _hoisted_19 = {
  key: 0,
  style: { "padding": "var(--space-3)", "color": "var(--color-ink-faint)" }
};
const _hoisted_20 = {
  key: 1,
  style: { "padding": "var(--space-3)", "color": "var(--color-ink-faint)" }
};
const _hoisted_21 = ["aria-selected", "onClick"];
const _hoisted_22 = { style: { "color": "var(--color-ink-faint)", "font-family": "var(--font-mono)" } };
const _hoisted_23 = { style: { "font-family": "var(--font-mono)" } };
const _hoisted_24 = ["value", "aria-valuetext"];
const _hoisted_25 = ["value", "aria-valuetext"];
const _hoisted_26 = { style: { "font-family": "var(--font-mono)" } };
const _hoisted_27 = {
  role: "group",
  "aria-label": "Durées courantes",
  style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-1-5)", "align-items": "center" }
};
const _hoisted_28 = ["value", "aria-valuetext"];
const _hoisted_29 = {
  viewBox: "0 0 1000 56",
  preserveAspectRatio: "none",
  "aria-hidden": "true",
  style: { "width": "100%", "height": "56px", "display": "block" }
};
const _hoisted_30 = ["x1", "x2"];
const _hoisted_31 = ["d"];
const _hoisted_32 = ["aria-checked", "onClick"];
const _hoisted_33 = { style: { "font-weight": "600", "font-size": "var(--text-sm)" } };
const _hoisted_34 = {
  key: 1,
  style: { "max-width": "12rem" }
};
const _hoisted_35 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-2)", "justify-content": "flex-end", "align-items": "center", "width": "100%" } };
const _hoisted_36 = { style: { "flex": "1", "min-width": "14rem", "font-size": "var(--text-sm)", "color": "var(--color-ink-muted)" } };
const _hoisted_37 = { style: { "color": "var(--color-ink)", "font-weight": "600" } };
const _sfc_main$3 = {
  __name: "Formulaire",
  props: { id: { type: Number, default: null }, etroit: Boolean },
  emits: ["retour", "enregistree"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const RACCOURCIS = [[31, "Semaine"], [96, "Week-end"], [127, "Tous"], [0, "Une seule fois"]];
    const CONTEXTES = [
      { v: "playlist", titre: "Une playlist", sous: "dans l'ordre ou mélangée" },
      { v: "bibliotheque", titre: "La bibliothèque", sous: "tirage, avec filtres" },
      { v: "artiste", titre: "Un artiste", sous: "tirage dans ses pistes" },
      { v: "album", titre: "Un album", sous: "tirage dans ses pistes" }
    ];
    const FINS = [
      { v: "duree", titre: "Après une durée", sous: "puis veille de l'ampli" },
      { v: "pistes", titre: "Après un nombre de pistes", sous: "puis veille de l'ampli" },
      { v: "sans_limite", titre: "Sans limite", sous: "jusqu'à ce qu'on arrête" }
    ];
    const CHAMPS = [
      "nom",
      "active",
      "heure",
      "jours",
      "contexte",
      "contexte_id",
      "melange",
      "genre_id",
      "format",
      "favoris",
      "volume_depart_db",
      "volume_cible_db",
      "montee_s",
      "fin_mode",
      "fin_valeur"
    ];
    const OU = {
      nom: "nom",
      heure: "heure",
      jours: "jours",
      contexte: "contexte",
      contexte_id: "contexte",
      melange: "contexte",
      genre_id: "genre",
      format: "format",
      favoris: "contexte",
      volume_depart_db: "dep",
      volume_cible_db: "cib",
      montee_s: "montee",
      fin_mode: "fin",
      fin_valeur: "fin"
    };
    const e = __hote$2.reactive({
      nom: "",
      active: true,
      heure: "07:00",
      jours: 31,
      contexte: "playlist",
      contexte_id: null,
      melange: false,
      genre_id: null,
      format: null,
      favoris: false,
      volume_depart_db: -50,
      volume_cible_db: -32,
      montee_s: 120,
      fin_mode: "duree",
      fin_valeur: 30
    });
    const er = __hote$2.reactive({});
    const erreurServeur = __hote$2.ref([]);
    const erreurChargement = __hote$2.ref("");
    const initiale = __hote$2.ref(null);
    const envoi = __hote$2.ref(false);
    const playlists = __hote$2.ref(null);
    const genres = __hote$2.ref(null);
    const recherche = __hote$2.ref("");
    const resultats = __hote$2.ref(null);
    const choisi = __hote$2.ref(false);
    __hote$2.onMounted(async () => {
      chargerPlaylists({ frais: true }).then((l) => {
        playlists.value = l;
        if (!props.id && e.contexte === "playlist" && e.contexte_id == null && l.length) e.contexte_id = premierePlaylist(l);
        if (!props.id && !l.length) e.contexte = "bibliotheque";
      });
      chargerGenres({ frais: true }).then((l) => {
        genres.value = l;
      });
      if (props.id) {
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
          recherche.value = (r == null ? void 0 : r.nom) || "";
          choisi.value = true;
          if (!r) coeur.artiste(a.contexte_id).then((x) => {
            recherche.value = nomArtiste(x);
          }).catch(() => {
          });
        } else if (a.contexte === "album" && a.contexte_id) {
          const r = etat.refs.albums[a.contexte_id];
          recherche.value = (r == null ? void 0 : r.nom) || "";
          choisi.value = true;
          if (!r) coeur.album(a.contexte_id).then((x) => {
            recherche.value = nomAlbum(x);
          }).catch(() => {
          });
        }
      }
    });
    const premierePlaylist = (l) => {
      var _a;
      return ((_a = l.find((p) => p.item_count > 0) || l[0]) == null ? void 0 : _a.id) ?? null;
    };
    const uniquePassee = __hote$2.computed(() => {
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
          const l = contexte === "artiste" ? (await coeur.artistes(q.trim())).map((a) => ({
            id: a.id,
            nom: nomArtiste(a),
            detail: a.track_count ? `${a.track_count} pistes` : `${a.album_count ?? 0} album${a.album_count > 1 ? "s" : ""}`
          })) : (await coeur.albums(q.trim())).map((a) => ({ id: a.id, nom: a.name, detail: a.artist_name, artiste: a.artist_name }));
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
    const fort = __hote$2.computed(() => e.volume_cible_db > SEUIL_FORT_DB);
    const apercu = __hote$2.computed(() => {
      void etat.maintenant;
      return prochaineApercu(e.heure, e.jours, etat.fuseau);
    });
    const courbe = __hote$2.computed(() => {
      const y = (v) => 50 - (v + 80) / 98 * 44;
      const x = e.montee_s / 3600 * 1e3;
      return `M0 ${y(e.volume_depart_db)} L${x} ${y(e.volume_cible_db)} L1000 ${y(e.volume_cible_db)}`;
    });
    const resume = __hote$2.computed(() => {
      const [l1, l2] = quoi(e);
      return `${libJours(e.jours)} · ${l1} (${l2}) · ${db(e.volume_depart_db)} → ${db(e.volume_cible_db)}${e.montee_s ? ` en ${duree(e.montee_s)}` : ""} · ${fin(e)}`;
    });
    function valider() {
      var _a, _b;
      const x = {};
      if (!e.nom.trim()) x.nom = "Donnez un nom à l'alarme, par exemple « Semaine ».";
      if (!/^\d{2}:\d{2}(:\d{2})?$/.test(e.heure || "")) x.heure = "Heure attendue au format HH:MM.";
      if (e.contexte === "playlist") {
        if (e.contexte_id == null) x.contexte = "Choisissez une playlist.";
        else if (((_b = (_a = playlists.value) == null ? void 0 : _a.find((p) => p.id === e.contexte_id)) == null ? void 0 : _b.item_count) === 0) x.contexte = "Cette playlist est vide : l'alarme n'aurait rien à jouer.";
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
    const majuscule = (s) => s ? s[0].toUpperCase() + s.slice(1) : s;
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
          erreurServeur.value = ["Cette alarme n'existe plus : elle a été supprimée entre-temps."];
          chargerAlarmes();
        } else {
          erreurServeur.value = [x.message];
        }
      } finally {
        envoi.value = false;
      }
    }
    const titreH1 = {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-3xl)",
      lineHeight: "var(--text-3xl-lh)",
      letterSpacing: "var(--text-3xl-ls)",
      fontWeight: 600,
      margin: "var(--space-1) 0 0"
    };
    const bloc = (i) => ({
      display: "flex",
      flexDirection: "column",
      gap: "var(--space-3)",
      borderTop: i ? "1px solid var(--color-border)" : void 0,
      paddingTop: i ? "var(--space-6)" : void 0,
      marginTop: i ? "var(--space-6)" : void 0
    });
    const titreBloc = { fontFamily: "var(--font-sans)", lineHeight: "var(--text-xs-lh)", fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--color-ink-muted)", margin: 0 };
    const libelle = { fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".04em", color: "var(--color-ink-muted)" };
    const indice = { fontSize: "var(--text-xs)", color: "var(--color-ink-faint)" };
    const erreurStyle = { fontSize: "var(--text-xs)", color: "var(--color-danger)" };
    const rangee = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: "var(--space-4)" };
    const colonne = { display: "flex", flexDirection: "column", gap: "var(--space-1-5)", minWidth: 0 };
    const choix = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "var(--space-2)" };
    const option = (on) => ({
      display: "flex",
      flexDirection: "column",
      gap: "2px",
      textAlign: "left",
      padding: "var(--space-3)",
      border: `1px solid var(--color-${on ? "primary" : "border-strong"})`,
      borderRadius: "var(--radius-md)",
      background: on ? "var(--color-primary-soft)" : "var(--color-surface)",
      cursor: "pointer",
      font: "inherit",
      color: on ? "var(--color-primary-ink)" : "var(--color-ink)",
      minHeight: "var(--touch-min)",
      boxShadow: on ? "inset 0 0 0 1px var(--color-primary)" : void 0
    });
    const curseur = { display: "flex", flexDirection: "column", gap: "var(--space-1-5)" };
    const curseurTete = { display: "flex", justifyContent: "space-between", alignItems: "baseline" };
    const range = { width: "100%", accentColor: "var(--color-primary)", minHeight: "var(--touch-min)" };
    const resultatStyle = (i, on) => ({
      all: "unset",
      cursor: "pointer",
      padding: "var(--space-2) var(--space-3)",
      display: "flex",
      justifyContent: "space-between",
      gap: "var(--space-2)",
      minHeight: "var(--touch-min)",
      alignItems: "center",
      borderTop: i ? "1px solid var(--color-border)" : void 0,
      background: on ? "var(--color-primary-soft)" : void 0,
      color: on ? "var(--color-primary-ink)" : void 0
    });
    return (_ctx, _cache) => {
      var _a;
      return __hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_1$3, [
        __hote$2.createElementVNode("div", _hoisted_2$3, [
          __hote$2.createElementVNode("span", _hoisted_3$3, [
            __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
              intent: "ghost",
              size: "sm",
              onClick: _cache[0] || (_cache[0] = ($event) => emit("retour"))
            }, {
              leading: __hote$2.withCtx(() => [
                __hote$2.createVNode(_sfc_main$6, { nom: "back" })
              ]),
              default: __hote$2.withCtx(() => [
                _cache[16] || (_cache[16] = __hote$2.createTextVNode("Réveil", -1))
              ]),
              _: 1
            })
          ]),
          __hote$2.createElementVNode("h1", { style: titreH1 }, __hote$2.toDisplayString(__props.id ? `Modifier « ${((_a = initiale.value) == null ? void 0 : _a.nom) || "sans nom"} »` : "Nouvelle alarme"), 1)
        ]),
        erreurServeur.value.length ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
          key: 0,
          ton: "danger",
          role: "alert",
          style: { "margin-bottom": "var(--space-4)" }
        }, {
          default: __hote$2.withCtx(() => [
            _cache[17] || (_cache[17] = __hote$2.createElementVNode("b", null, "Enregistrement refusé par le serveur.", -1)),
            (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(erreurServeur.value, (m, i) => {
              return __hote$2.openBlock(), __hote$2.createElementBlock("span", { key: i }, __hote$2.toDisplayString(m), 1);
            }), 128))
          ]),
          _: 1
        })) : __hote$2.createCommentVNode("", true),
        __props.id && !initiale.value && !erreurChargement.value ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiSkeleton), {
          key: 1,
          rows: 4,
          cols: 1
        })) : erreurChargement.value ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiErrorState), {
          key: 2,
          message: erreurChargement.value,
          "retry-label": "Revenir à la liste",
          onRetry: _cache[1] || (_cache[1] = ($event) => emit("retour"))
        }, null, 8, ["message"])) : (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiPanel), {
          key: 3,
          as: "form",
          padding: "md",
          novalidate: "",
          onSubmit: __hote$2.withModifiers(enregistrer, ["prevent"])
        }, {
          footer: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("div", _hoisted_35, [
              __hote$2.createElementVNode("span", _hoisted_36, [
                __hote$2.createElementVNode("b", _hoisted_37, __hote$2.toDisplayString(e.heure ? __hote$2.unref(hm)(e.heure) : "—"), 1),
                __hote$2.createTextVNode(" " + __hote$2.toDisplayString(resume.value), 1)
              ]),
              __hote$2.createElementVNode("span", {
                style: __hote$2.normalizeStyle({ display: "inline-flex", flex: __props.etroit ? 1 : void 0 })
              }, [
                __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                  intent: "ghost",
                  size: "md",
                  block: "",
                  onClick: _cache[15] || (_cache[15] = ($event) => emit("retour"))
                }, {
                  default: __hote$2.withCtx(() => [..._cache[28] || (_cache[28] = [
                    __hote$2.createTextVNode("Annuler", -1)
                  ])]),
                  _: 1
                })
              ], 4),
              __hote$2.createElementVNode("span", {
                style: __hote$2.normalizeStyle({ display: "inline-flex", flex: __props.etroit ? 1 : void 0 })
              }, [
                __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                  intent: "primary",
                  size: "md",
                  type: "submit",
                  block: "",
                  loading: envoi.value
                }, {
                  default: __hote$2.withCtx(() => [..._cache[29] || (_cache[29] = [
                    __hote$2.createTextVNode("Enregistrer", -1)
                  ])]),
                  _: 1
                }, 8, ["loading"])
              ], 4)
            ])
          ]),
          default: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("div", _hoisted_4$3, [
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(bloc(0))
              }, [
                __hote$2.createElementVNode("h2", { style: titreBloc }, "Quand"),
                __hote$2.createElementVNode("div", {
                  style: __hote$2.normalizeStyle({ display: "grid", gap: "var(--space-4)", gridTemplateColumns: __props.etroit ? "1fr" : "minmax(0,2fr) minmax(8rem,1fr)" })
                }, [
                  __hote$2.createVNode(__hote$2.unref(__hote.UiField), {
                    "model-value": e.nom,
                    label: "Nom",
                    placeholder: "Semaine",
                    error: er.nom,
                    "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => champ("nom", $event))
                  }, null, 8, ["model-value", "error"]),
                  __hote$2.createVNode(__hote$2.unref(__hote.UiField), {
                    "model-value": e.heure,
                    label: "Heure",
                    type: "time",
                    error: er.heure,
                    hint: `Heure de ${__hote$2.unref(etat).fuseau}`,
                    "onUpdate:modelValue": _cache[3] || (_cache[3] = ($event) => champ("heure", $event))
                  }, null, 8, ["model-value", "error", "hint"])
                ], 4),
                __hote$2.createElementVNode("div", _hoisted_5$3, [
                  __hote$2.createElementVNode("span", { style: libelle }, "Jours"),
                  __hote$2.createElementVNode("div", _hoisted_6$3, [
                    (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(__hote$2.unref(JOURS), (j, i) => {
                      return __hote$2.openBlock(), __hote$2.createElementBlock("span", {
                        key: i,
                        style: { "display": "inline-flex", "width": "var(--space-9)" }
                      }, [
                        __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                          interactive: "",
                          pressed: !!(e.jours & 1 << i),
                          "aria-label": __hote$2.unref(JOURS_LONGS)[i],
                          style: { "width": "100%", "justify-content": "center", "padding": "0" },
                          onClick: ($event) => champ("jours", e.jours ^ 1 << i)
                        }, {
                          default: __hote$2.withCtx(() => [
                            __hote$2.createTextVNode(__hote$2.toDisplayString(j), 1)
                          ]),
                          _: 2
                        }, 1032, ["pressed", "aria-label", "onClick"])
                      ]);
                    }), 128)),
                    _cache[18] || (_cache[18] = __hote$2.createElementVNode("span", {
                      "aria-hidden": "true",
                      style: { "width": "1px", "height": "20px", "background": "var(--color-border)", "margin": "0 var(--space-1)" }
                    }, null, -1)),
                    (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(RACCOURCIS, ([v, l]) => {
                      return __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                        key: v,
                        interactive: "",
                        pressed: e.jours === v,
                        onClick: ($event) => champ("jours", v)
                      }, {
                        default: __hote$2.withCtx(() => [
                          __hote$2.createTextVNode(__hote$2.toDisplayString(l), 1)
                        ]),
                        _: 2
                      }, 1032, ["pressed", "onClick"]);
                    }), 64))
                  ]),
                  er.jours ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                    key: 0,
                    style: erreurStyle
                  }, __hote$2.toDisplayString(er.jours), 1)) : (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                    key: 1,
                    style: indice
                  }, [
                    __hote$2.createTextVNode(__hote$2.toDisplayString(e.jours === 0 ? "Une seule fois : l'alarme se désactive après son passage. " : ""), 1),
                    !e.active ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                      __hote$2.createTextVNode("Désactivée : elle ne sonnera pas.")
                    ], 64)) : apercu.value ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                      _cache[19] || (_cache[19] = __hote$2.createTextVNode("Prochaine : ", -1)),
                      __hote$2.createElementVNode("b", _hoisted_7$2, __hote$2.toDisplayString(apercu.value), 1)
                    ], 64)) : __hote$2.createCommentVNode("", true)
                  ]))
                ]),
                __hote$2.createElementVNode("div", _hoisted_8$2, [
                  __hote$2.createVNode(__hote$2.unref(__hote.UiSwitch), {
                    "model-value": e.active,
                    "aria-labelledby": "denon-lib-active",
                    "onUpdate:modelValue": _cache[4] || (_cache[4] = ($event) => champ("active", $event))
                  }, null, 8, ["model-value"]),
                  _cache[20] || (_cache[20] = __hote$2.createElementVNode("span", { id: "denon-lib-active" }, "Active", -1))
                ])
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(bloc(1))
              }, [
                __hote$2.createElementVNode("h2", { style: titreBloc }, "Ce qui se joue"),
                __hote$2.createElementVNode("div", {
                  role: "radiogroup",
                  "aria-label": "Ce qui se joue",
                  style: choix
                }, [
                  (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(CONTEXTES, (o) => {
                    return __hote$2.createElementVNode("button", {
                      key: o.v,
                      type: "button",
                      role: "radio",
                      "aria-checked": e.contexte === o.v,
                      style: __hote$2.normalizeStyle(option(e.contexte === o.v)),
                      onClick: ($event) => choisirContexte(o.v)
                    }, [
                      __hote$2.createElementVNode("b", _hoisted_10$2, __hote$2.toDisplayString(o.titre), 1),
                      __hote$2.createElementVNode("span", {
                        style: __hote$2.normalizeStyle({ fontSize: "var(--text-xs)", color: e.contexte === o.v ? "var(--color-primary-ink)" : "var(--color-ink-muted)" })
                      }, __hote$2.toDisplayString(o.sous), 5)
                    ], 12, _hoisted_9$2);
                  }), 64))
                ]),
                __hote$2.createElementVNode("div", _hoisted_11$1, [
                  e.contexte === "playlist" ? (__hote$2.openBlock(), __hote$2.createElementBlock("div", {
                    key: 0,
                    style: rangee
                  }, [
                    __hote$2.createElementVNode("div", { style: colonne }, [
                      __hote$2.createVNode(__hote$2.unref(__hote.UiSelect), {
                        "model-value": e.contexte_id ?? "",
                        label: "Playlist",
                        block: "",
                        "onUpdate:modelValue": _cache[5] || (_cache[5] = ($event) => champ("contexte_id", $event === "" ? null : +$event))
                      }, {
                        default: __hote$2.withCtx(() => [
                          __hote$2.createElementVNode("option", _hoisted_12$1, __hote$2.toDisplayString(playlists.value === null ? "Chargement…" : playlists.value.length ? "Choisir une playlist" : "Aucune playlist"), 1),
                          (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(playlists.value || [], (p) => {
                            return __hote$2.openBlock(), __hote$2.createElementBlock("option", {
                              key: p.id,
                              value: p.id
                            }, __hote$2.toDisplayString(p.name) + " (" + __hote$2.toDisplayString(p.item_count) + " piste" + __hote$2.toDisplayString(p.item_count > 1 ? "s" : "") + ")", 9, _hoisted_13$1);
                          }), 128))
                        ]),
                        _: 1
                      }, 8, ["model-value"]),
                      er.contexte ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                        key: 0,
                        style: erreurStyle
                      }, __hote$2.toDisplayString(er.contexte), 1)) : playlists.value && !playlists.value.length ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                        key: 1,
                        style: indice
                      }, "Créez une playlist dans le player d'abord.")) : __hote$2.createCommentVNode("", true)
                    ]),
                    __hote$2.createElementVNode("div", { style: colonne }, [
                      __hote$2.createElementVNode("span", { style: libelle }, "Ordre"),
                      __hote$2.createElementVNode("div", _hoisted_14$1, [
                        __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                          interactive: "",
                          pressed: !e.melange,
                          onClick: _cache[6] || (_cache[6] = ($event) => champ("melange", false))
                        }, {
                          default: __hote$2.withCtx(() => [..._cache[21] || (_cache[21] = [
                            __hote$2.createTextVNode("Dans l'ordre", -1)
                          ])]),
                          _: 1
                        }, 8, ["pressed"]),
                        __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                          interactive: "",
                          pressed: e.melange,
                          onClick: _cache[7] || (_cache[7] = ($event) => champ("melange", true))
                        }, {
                          default: __hote$2.withCtx(() => [..._cache[22] || (_cache[22] = [
                            __hote$2.createTextVNode("Mélangée", -1)
                          ])]),
                          _: 1
                        }, 8, ["pressed"])
                      ])
                    ])
                  ])) : e.contexte === "bibliotheque" ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                    __hote$2.createElementVNode("div", { style: rangee }, [
                      __hote$2.createElementVNode("div", { style: colonne }, [
                        __hote$2.createVNode(__hote$2.unref(__hote.UiSelect), {
                          "model-value": e.genre_id ?? "",
                          label: "Genre",
                          block: "",
                          "onUpdate:modelValue": _cache[8] || (_cache[8] = ($event) => champ("genre_id", $event === "" ? null : +$event))
                        }, {
                          default: __hote$2.withCtx(() => [
                            _cache[23] || (_cache[23] = __hote$2.createElementVNode("option", { value: "" }, "Tous les genres", -1)),
                            (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(genres.value || [], (g) => {
                              return __hote$2.openBlock(), __hote$2.createElementBlock("option", {
                                key: g.id,
                                value: g.id
                              }, __hote$2.toDisplayString(g.name), 9, _hoisted_15$1);
                            }), 128))
                          ]),
                          _: 1
                        }, 8, ["model-value"]),
                        er.genre ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                          key: 0,
                          style: erreurStyle
                        }, __hote$2.toDisplayString(er.genre), 1)) : __hote$2.createCommentVNode("", true)
                      ]),
                      __hote$2.createElementVNode("div", { style: colonne }, [
                        __hote$2.createVNode(__hote$2.unref(__hote.UiSelect), {
                          "model-value": e.format ?? "",
                          label: "Format",
                          block: "",
                          "onUpdate:modelValue": _cache[9] || (_cache[9] = ($event) => champ("format", $event || null))
                        }, {
                          default: __hote$2.withCtx(() => [
                            _cache[24] || (_cache[24] = __hote$2.createElementVNode("option", { value: "" }, "Tous les formats", -1)),
                            (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(__hote$2.unref(FORMATS), (f) => {
                              return __hote$2.openBlock(), __hote$2.createElementBlock("option", {
                                key: f,
                                value: f
                              }, __hote$2.toDisplayString(f), 9, _hoisted_16$1);
                            }), 128))
                          ]),
                          _: 1
                        }, 8, ["model-value"]),
                        er.format ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                          key: 0,
                          style: erreurStyle
                        }, __hote$2.toDisplayString(er.format), 1)) : __hote$2.createCommentVNode("", true)
                      ]),
                      __hote$2.createElementVNode("div", { style: colonne }, [
                        __hote$2.createElementVNode("span", {
                          style: libelle,
                          id: "denon-lib-fav"
                        }, "Favoris"),
                        __hote$2.createElementVNode("div", _hoisted_17, [
                          __hote$2.createVNode(__hote$2.unref(__hote.UiSwitch), {
                            "model-value": e.favoris,
                            "aria-labelledby": "denon-lib-fav-texte",
                            "onUpdate:modelValue": _cache[10] || (_cache[10] = ($event) => champ("favoris", $event))
                          }, null, 8, ["model-value"]),
                          _cache[25] || (_cache[25] = __hote$2.createElementVNode("span", { id: "denon-lib-fav-texte" }, "Favoris seulement", -1))
                        ])
                      ])
                    ]),
                    __hote$2.createElementVNode("span", { style: indice }, "Le tirage suit les mêmes règles que l'aléatoire du player : il évite ce qui a joué cette semaine.")
                  ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 2 }, [
                    __hote$2.createElementVNode("div", { style: colonne }, [
                      __hote$2.createVNode(__hote$2.unref(__hote.UiField), {
                        "model-value": recherche.value,
                        label: e.contexte === "artiste" ? "Artiste" : "Album",
                        placeholder: e.contexte === "artiste" ? "Chercher un artiste" : "Chercher un album ou son artiste",
                        error: er.contexte,
                        autocomplete: "off",
                        "onUpdate:modelValue": chercher
                      }, {
                        leading: __hote$2.withCtx(() => [
                          __hote$2.createVNode(_sfc_main$6, { nom: "search" })
                        ]),
                        _: 1
                      }, 8, ["model-value", "label", "placeholder", "error"])
                    ]),
                    recherche.value.trim() && !choisi.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("div", {
                      key: 0,
                      role: "listbox",
                      "aria-label": e.contexte === "artiste" ? "Artistes" : "Albums",
                      style: { "display": "flex", "flex-direction": "column", "border": "1px solid var(--color-border)", "border-radius": "var(--radius-md)", "background": "var(--color-surface)", "max-height": "11rem", "overflow": "auto" }
                    }, [
                      resultats.value === null ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_19, "Recherche…")) : !resultats.value.length ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_20, __hote$2.toDisplayString(e.contexte === "artiste" ? "Aucun artiste ne correspond." : "Aucun album ne correspond."), 1)) : __hote$2.createCommentVNode("", true),
                      (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(resultats.value || [], (r, i) => {
                        return __hote$2.openBlock(), __hote$2.createElementBlock("button", {
                          key: r.id,
                          type: "button",
                          role: "option",
                          "aria-selected": e.contexte_id === r.id,
                          style: __hote$2.normalizeStyle(resultatStyle(i, e.contexte_id === r.id)),
                          onClick: ($event) => prendre(r)
                        }, [
                          __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(r.nom), 1),
                          __hote$2.createElementVNode("span", _hoisted_22, __hote$2.toDisplayString(r.detail), 1)
                        ], 12, _hoisted_21);
                      }), 128))
                    ], 8, _hoisted_18)) : choisi.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 1,
                      style: indice
                    }, "Tirage dans les pistes " + __hote$2.toDisplayString(e.contexte === "artiste" ? "de l'artiste" : "de l'album") + ", comme l'aléatoire du player.", 1)) : __hote$2.createCommentVNode("", true)
                  ], 64))
                ])
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(bloc(2))
              }, [
                __hote$2.createElementVNode("h2", { style: titreBloc }, "Volume"),
                __hote$2.createElementVNode("div", { style: rangee }, [
                  __hote$2.createElementVNode("div", { style: curseur }, [
                    __hote$2.createElementVNode("div", { style: curseurTete }, [
                      __hote$2.createElementVNode("label", {
                        style: libelle,
                        for: "denon-dep"
                      }, "Volume de départ"),
                      __hote$2.createElementVNode("span", _hoisted_23, __hote$2.toDisplayString(__hote$2.unref(db)(e.volume_depart_db)), 1)
                    ]),
                    __hote$2.createElementVNode("input", {
                      id: "denon-dep",
                      type: "range",
                      min: "-80",
                      max: "18",
                      step: "0.5",
                      value: e.volume_depart_db,
                      "aria-valuetext": __hote$2.unref(db)(e.volume_depart_db),
                      style: range,
                      onInput: _cache[11] || (_cache[11] = ($event) => champ("volume_depart_db", +$event.target.value))
                    }, null, 40, _hoisted_24),
                    er.dep ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 0,
                      style: erreurStyle
                    }, __hote$2.toDisplayString(er.dep), 1)) : __hote$2.createCommentVNode("", true)
                  ]),
                  __hote$2.createElementVNode("div", { style: curseur }, [
                    __hote$2.createElementVNode("div", { style: curseurTete }, [
                      __hote$2.createElementVNode("label", {
                        style: libelle,
                        for: "denon-cib"
                      }, "Volume cible"),
                      __hote$2.createElementVNode("span", {
                        style: __hote$2.normalizeStyle({ fontFamily: "var(--font-mono)", color: fort.value ? "var(--color-warning)" : void 0 })
                      }, __hote$2.toDisplayString(__hote$2.unref(db)(e.volume_cible_db)), 5)
                    ]),
                    __hote$2.createElementVNode("input", {
                      id: "denon-cib",
                      type: "range",
                      min: "-80",
                      max: "18",
                      step: "0.5",
                      value: e.volume_cible_db,
                      "aria-valuetext": __hote$2.unref(db)(e.volume_cible_db),
                      style: range,
                      onInput: _cache[12] || (_cache[12] = ($event) => champ("volume_cible_db", +$event.target.value))
                    }, null, 40, _hoisted_25),
                    er.cib ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 0,
                      style: erreurStyle
                    }, __hote$2.toDisplayString(er.cib), 1)) : fort.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: 1,
                      style: __hote$2.normalizeStyle({ ...indice, color: "var(--color-warning)" })
                    }, "Fort pour un réveil : l'ampli affiche −15 dB comme un volume déjà soutenu.", 4)) : __hote$2.createCommentVNode("", true)
                  ])
                ]),
                __hote$2.createElementVNode("div", { style: curseur }, [
                  __hote$2.createElementVNode("div", { style: curseurTete }, [
                    __hote$2.createElementVNode("label", {
                      style: libelle,
                      for: "denon-montee"
                    }, "Durée de la montée"),
                    __hote$2.createElementVNode("span", _hoisted_26, __hote$2.toDisplayString(e.montee_s === 0 ? "aucune : volume cible d'emblée" : __hote$2.unref(duree)(e.montee_s)), 1)
                  ]),
                  __hote$2.createElementVNode("div", _hoisted_27, [
                    (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(__hote$2.unref(PRESETS_MONTEE), (m) => {
                      return __hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiChip), {
                        key: m,
                        interactive: "",
                        pressed: e.montee_s === m,
                        onClick: ($event) => champ("montee_s", m)
                      }, {
                        default: __hote$2.withCtx(() => [
                          __hote$2.createTextVNode(__hote$2.toDisplayString(m === 0 ? "Aucune" : __hote$2.unref(duree)(m)), 1)
                        ]),
                        _: 2
                      }, 1032, ["pressed", "onClick"]);
                    }), 128))
                  ]),
                  __hote$2.createElementVNode("input", {
                    id: "denon-montee",
                    type: "range",
                    min: "0",
                    max: "3600",
                    step: "30",
                    value: e.montee_s,
                    "aria-valuetext": e.montee_s === 0 ? "aucune" : __hote$2.unref(duree)(e.montee_s),
                    style: range,
                    onInput: _cache[13] || (_cache[13] = ($event) => champ("montee_s", +$event.target.value))
                  }, null, 40, _hoisted_28),
                  (__hote$2.openBlock(), __hote$2.createElementBlock("svg", _hoisted_29, [
                    _cache[26] || (_cache[26] = __hote$2.createElementVNode("line", {
                      x1: "0",
                      x2: "1000",
                      y1: "50",
                      y2: "50",
                      stroke: "var(--color-border)",
                      "vector-effect": "non-scaling-stroke"
                    }, null, -1)),
                    (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList([250, 500, 750], (x) => {
                      return __hote$2.createElementVNode("line", {
                        key: x,
                        x1: x,
                        x2: x,
                        y1: "46",
                        y2: "54",
                        stroke: "var(--color-border)",
                        "vector-effect": "non-scaling-stroke"
                      }, null, 8, _hoisted_30);
                    }), 64)),
                    __hote$2.createElementVNode("path", {
                      d: courbe.value,
                      fill: "none",
                      stroke: "var(--color-primary)",
                      "stroke-width": "2",
                      "vector-effect": "non-scaling-stroke"
                    }, null, 8, _hoisted_31)
                  ])),
                  _cache[27] || (_cache[27] = __hote$2.createElementVNode("div", {
                    "aria-hidden": "true",
                    style: { "display": "flex", "justify-content": "space-between", "font-family": "var(--font-mono)", "font-size": "11px", "color": "var(--color-ink-faint)", "margin-top": "calc(-1 * var(--space-1))" }
                  }, [
                    __hote$2.createElementVNode("span", null, "0"),
                    __hote$2.createElementVNode("span", null, "15 min"),
                    __hote$2.createElementVNode("span", null, "30 min"),
                    __hote$2.createElementVNode("span", null, "45 min"),
                    __hote$2.createElementVNode("span", null, "1 h")
                  ], -1)),
                  er.montee ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                    key: 0,
                    style: erreurStyle
                  }, __hote$2.toDisplayString(er.montee), 1)) : __hote$2.createCommentVNode("", true)
                ]),
                __hote$2.createElementVNode("span", { style: indice }, "Par pas de 0,5 dB. La montée s'arrête si quelqu'un touche au volume." + __hote$2.toDisplayString(e.volume_depart_db > e.volume_cible_db ? " Le départ est plus fort que la cible : le volume descendra." : ""), 1)
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(bloc(3))
              }, [
                __hote$2.createElementVNode("h2", { style: titreBloc }, "Fin"),
                __hote$2.createElementVNode("div", {
                  role: "radiogroup",
                  "aria-label": "Fin",
                  style: choix
                }, [
                  (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(FINS, (o) => {
                    return __hote$2.createElementVNode("button", {
                      key: o.v,
                      type: "button",
                      role: "radio",
                      "aria-checked": e.fin_mode === o.v,
                      style: __hote$2.normalizeStyle(option(e.fin_mode === o.v)),
                      onClick: ($event) => choisirFin(o.v)
                    }, [
                      __hote$2.createElementVNode("b", _hoisted_33, __hote$2.toDisplayString(o.titre), 1),
                      __hote$2.createElementVNode("span", {
                        style: __hote$2.normalizeStyle({ fontSize: "var(--text-xs)", color: e.fin_mode === o.v ? "var(--color-primary-ink)" : "var(--color-ink-muted)" })
                      }, __hote$2.toDisplayString(o.sous), 5)
                    ], 12, _hoisted_32);
                  }), 64))
                ]),
                e.fin_mode === "sans_limite" ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                  key: 0,
                  style: indice
                }, "Le tirage se relance quand il s'épuise. L'ampli reste allumé.")) : (__hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_34, [
                  __hote$2.createVNode(__hote$2.unref(__hote.UiField), {
                    "model-value": e.fin_valeur ?? "",
                    type: "number",
                    min: "1",
                    max: e.fin_mode === "duree" ? 1440 : 1e3,
                    label: e.fin_mode === "duree" ? "Durée (min)" : "Nombre de pistes",
                    error: er.fin,
                    block: "",
                    "onUpdate:modelValue": _cache[14] || (_cache[14] = ($event) => champ("fin_valeur", $event === "" ? null : Number($event)))
                  }, null, 8, ["model-value", "max", "label", "error"])
                ])),
                __hote$2.createElementVNode("span", { style: indice }, "Pour couper le réveil : « Arrêter », la veille, une autre entrée, la sourdine ou la pause. L'ampli lâche parfois la lecture seul : un Stop en milieu de piste, même à la télécommande, est relancé deux fois.")
              ], 4)
            ])
          ]),
          _: 1
        }))
      ]);
    };
  }
};
const _hoisted_1$2 = {
  "data-test": "denon-alarmes",
  style: { "display": "flex", "flex-direction": "column", "background": "var(--color-surface)", "border": "1px solid var(--color-border)", "border-radius": "var(--radius-lg)", "overflow": "hidden" }
};
const _hoisted_2$2 = ["data-test"];
const _hoisted_3$2 = {
  key: 0,
  style: { "font-size": "var(--text-xs)" }
};
const _hoisted_4$2 = { style: { "font-weight": "600", "font-size": "var(--text-sm)", "margin-top": "2px" } };
const _hoisted_5$2 = {
  key: 0,
  style: { "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)" }
};
const _hoisted_6$2 = ["aria-label"];
const _hoisted_7$1 = { style: { "white-space": "nowrap", "overflow": "hidden", "text-overflow": "ellipsis" } };
const _hoisted_8$1 = { style: { "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)" } };
const _hoisted_9$1 = { style: { "color": "var(--color-ink)", "font-weight": "600", "font-family": "var(--font-mono)" } };
const _hoisted_10$1 = { style: { "color": "var(--color-ink)", "font-weight": "600" } };
const _hoisted_11 = ["title"];
const _hoisted_12 = {
  key: 0,
  style: { "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)" }
};
const _hoisted_13 = {
  key: 0,
  role: "alert",
  style: { "grid-column": "1 / -1", "display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "var(--space-2)", "padding": "var(--space-2-5) var(--space-3)", "background": "var(--color-danger-soft)", "border-radius": "var(--radius-md)" }
};
const _hoisted_14 = { style: { "flex": "1", "min-width": "12rem" } };
const _hoisted_15 = ["href"];
const _hoisted_16 = { style: { "display": "flex", "flex-wrap": "wrap", "justify-content": "space-between", "gap": "var(--space-2)", "margin-top": "var(--space-2)", "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)" } };
const _sfc_main$2 = {
  __name: "Liste",
  props: { etroit: Boolean },
  emits: ["nouvelle", "modifier", "diagnostic", "essaye"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const aSupprimer = __hote$2.ref(null);
    const essai = __hote$2.ref(null);
    const enCours = __hote$2.reactive({});
    const retours = __hote$2.reactive({});
    const erreurGeste = __hote$2.ref("");
    const t = __hote$2.computed(() => etat.test);
    const lignes = __hote$2.computed(() => {
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
    const actives = __hote$2.computed(() => (etat.alarmes || []).filter((a) => a.active && !a.test).length);
    const estInactive = (l) => !l.test && !l.a.active;
    const reste = __hote$2.computed(() => Math.max(0, Math.ceil((t.value.echeanceMs - etat.maintenant) / 1e3)));
    const heurePlus10 = __hote$2.computed(() => {
      const [h, m, s] = t.value.heure.split(":").map(Number);
      const tot = (h * 3600 + m * 60 + s + 10) % 86400;
      return [Math.floor(tot / 3600), Math.floor(tot % 3600 / 60), tot % 60].map((n) => String(n).padStart(2, "0")).join(":");
    });
    const heureDepart = __hote$2.computed(() => t.value.heure);
    const suite = __hote$2.computed(() => suiteDuTest(t.value));
    async function reessayer() {
      etat.erreurListe = null;
      etat.alarmes = null;
      await chargerAlarmes();
    }
    function introuvable(a, e) {
      if (e.code !== "alarme_introuvable") return false;
      erreurGeste.value = `« ${a.nom} » : cette alarme n'existe plus.`;
      aSupprimer.value = null;
      chargerAlarmes();
      return true;
    }
    async function basculer(a, active) {
      enCours[a.id] = true;
      erreurGeste.value = "";
      try {
        const r = await reveil.modifier(a.id, { active });
        Object.assign(a, r);
      } catch (e) {
        if (!introuvable(a, e)) erreurGeste.value = `« ${a.nom} » n'a pas pu être ${active ? "activée" : "désactivée"} : ${e.message}`;
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
        if (!introuvable(a, e)) erreurGeste.value = `« ${a.nom} » n'a pas pu être supprimée : ${e.message}`;
      } finally {
        enCours[a.id] = false;
      }
    }
    const RETOURS = {
      ampli_injoignable: (e) => ({ titre: "Rien n'a joué : l'ampli ne répond pas.", texte: `Vérifiez qu'il est branché et que le contrôle réseau reste actif en veille (${e.message}).`, diagnostic: true }),
      adresse_reseau_non_reglee: (e) => ({ titre: "Rien n'a joué : l'ampli ne saurait pas où chercher la musique.", texte: "L'adresse d'unisson sur le réseau n'est pas réglée.", reglage: e.reglage }),
      aucune_piste: (e) => ({ titre: "Rien n'a joué : il n'y a rien à jouer.", texte: `${e.message}.` }),
      aucun_format_commun: (e) => ({ titre: "Rien n'a joué : aucun format lisible par l'ampli.", texte: `${e.message}.`, diagnostic: true })
    };
    async function essayer(a) {
      delete retours[a.id];
      erreurGeste.value = "";
      essai.value = a.id;
      try {
        await reveil.essayer(a.id);
        await chargerSeance({ force: true });
        emit("essaye", a);
      } catch (e) {
        if (introuvable(a, e)) return;
        const f = RETOURS[e.code];
        retours[a.id] = f ? f(e) : { titre: "Rien n'a joué.", texte: e.message, diagnostic: e.statut === 409 };
        emit("essaye", a, e);
        await chargerSeance({ force: true });
      } finally {
        essai.value = null;
        chargerAlarmes();
      }
    }
    function ligne(l, i) {
      return {
        display: "grid",
        gridTemplateColumns: props.etroit ? "auto minmax(0, 1fr) auto" : "auto 7.5rem minmax(0,1.4fr) minmax(0,1fr) auto",
        gridTemplateAreas: props.etroit ? '"sw heure act" "quoi quoi quoi" "etat etat etat"' : void 0,
        rowGap: props.etroit ? "var(--space-2-5)" : void 0,
        columnGap: "var(--space-4)",
        alignItems: "center",
        padding: "var(--space-4)",
        borderTop: i ? "1px solid var(--color-border)" : void 0,
        background: l.test ? "var(--color-surface-2)" : void 0
      };
    }
    function zone(nom) {
      if (!props.etroit) return {};
      const z = { gridArea: nom };
      if (nom === "sw" || nom === "act") Object.assign(z, { alignSelf: "start" });
      if (nom === "sw") z.marginTop = "4px";
      return z;
    }
    const etatStyle = __hote$2.computed(() => ({
      ...zone("etat"),
      display: "flex",
      flexDirection: props.etroit ? "row" : "column",
      flexWrap: props.etroit ? "wrap" : void 0,
      alignItems: props.etroit ? "center" : "flex-start",
      gap: "var(--space-1-5)",
      minWidth: 0
    }));
    const heureStyle = {
      fontFamily: "var(--font-mono)",
      fontVariantNumeric: "tabular-nums",
      fontSize: "var(--text-xl)",
      fontWeight: 500,
      letterSpacing: "-0.02em",
      lineHeight: 1.1
    };
    const petit = { fontSize: "var(--text-xs)", color: "var(--color-ink-muted)" };
    const jour = (on) => ({
      fontFamily: "var(--font-mono)",
      fontSize: "10px",
      width: "15px",
      height: "15px",
      display: "grid",
      placeItems: "center",
      borderRadius: "3px",
      color: on ? "var(--color-primary-ink)" : "var(--color-ink-faint)",
      background: on ? "var(--color-primary-soft)" : void 0,
      fontWeight: on ? 600 : void 0
    });
    return (_ctx, _cache) => {
      return __hote$2.unref(etat).alarmes === null && !__hote$2.unref(etat).erreurListe ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiSkeleton), {
        key: 0,
        rows: 3,
        cols: 1
      })) : __hote$2.unref(etat).erreurListe && __hote$2.unref(etat).alarmes === null ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiErrorState), {
        key: 1,
        message: `Les alarmes n'ont pas pu être chargées : ${__hote$2.unref(etat).erreurListe.message}`,
        "retry-label": "Réessayer",
        onRetry: reessayer
      }, null, 8, ["message"])) : !lignes.value.length ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiEmpty), {
        key: 2,
        eyebrow: "Réveil",
        title: "Aucune alarme pour l'instant",
        description: "Une alarme allume l'ampli à l'heure dite, monte doucement le volume et joue une playlist ou un tirage de la bibliothèque."
      }, {
        actions: __hote$2.withCtx(() => [
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "primary",
            size: "md",
            onClick: _cache[0] || (_cache[0] = ($event) => emit("nouvelle"))
          }, {
            leading: __hote$2.withCtx(() => [
              __hote$2.createVNode(_sfc_main$6, { nom: "plus" })
            ]),
            default: __hote$2.withCtx(() => [
              _cache[5] || (_cache[5] = __hote$2.createTextVNode("Nouvelle alarme", -1))
            ]),
            _: 1
          }),
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "secondary",
            size: "md",
            onClick: _cache[1] || (_cache[1] = ($event) => emit("diagnostic"))
          }, {
            default: __hote$2.withCtx(() => [..._cache[6] || (_cache[6] = [
              __hote$2.createTextVNode("Vérifier l'ampli d'abord", -1)
            ])]),
            _: 1
          })
        ]),
        _: 1
      })) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 3 }, [
        erreurGeste.value ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
          key: 0,
          ton: "danger",
          role: "alert",
          style: { "margin-bottom": "var(--space-3)" }
        }, {
          actions: __hote$2.withCtx(() => [
            __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
              intent: "ghost",
              size: "sm",
              onClick: _cache[2] || (_cache[2] = ($event) => erreurGeste.value = "")
            }, {
              default: __hote$2.withCtx(() => [..._cache[7] || (_cache[7] = [
                __hote$2.createTextVNode("Fermer", -1)
              ])]),
              _: 1
            })
          ]),
          default: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(erreurGeste.value), 1)
          ]),
          _: 1
        })) : __hote$2.createCommentVNode("", true),
        __hote$2.createElementVNode("div", _hoisted_1$2, [
          (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(lignes.value, (l, i) => {
            return __hote$2.openBlock(), __hote$2.createElementBlock("div", {
              key: l.cle,
              "data-test": l.test ? "denon-ligne-test" : "denon-ligne",
              style: __hote$2.normalizeStyle(ligne(l, i))
            }, [
              __hote$2.createElementVNode("span", {
                style: __hote$2.normalizeStyle(zone("sw"))
              }, [
                l.test ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiChip), {
                  key: 0,
                  tone: "accent"
                }, {
                  default: __hote$2.withCtx(() => [..._cache[8] || (_cache[8] = [
                    __hote$2.createTextVNode("Test", -1)
                  ])]),
                  _: 1
                })) : (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiSwitch), {
                  key: 1,
                  "model-value": l.a.active,
                  label: `Alarme « ${l.a.nom} » active`,
                  disabled: enCours[l.a.id],
                  "onUpdate:modelValue": ($event) => basculer(l.a, $event)
                }, null, 8, ["model-value", "label", "disabled", "onUpdate:modelValue"]))
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(zone("heure"))
              }, [
                __hote$2.createElementVNode("div", {
                  style: __hote$2.normalizeStyle({ ...heureStyle, color: estInactive(l) ? "var(--color-ink-faint)" : void 0 })
                }, [
                  __hote$2.createTextVNode(__hote$2.toDisplayString(l.test ? l.heure.slice(0, 5) : __hote$2.unref(hm)(l.a.heure)), 1),
                  l.test ? (__hote$2.openBlock(), __hote$2.createElementBlock("small", _hoisted_3$2, __hote$2.toDisplayString(l.heure.slice(5)), 1)) : __hote$2.createCommentVNode("", true)
                ], 4),
                __hote$2.createElementVNode("div", _hoisted_4$2, __hote$2.toDisplayString(l.test ? l.nom : l.a.nom), 1),
                l.test || l.a.jours === 0 ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_5$2, "une seule fois")) : (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                  key: 1,
                  "aria-label": __hote$2.unref(libJours)(l.a.jours),
                  style: { "display": "inline-flex", "gap": "2px", "margin-top": "var(--space-1)" }
                }, [
                  (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(__hote$2.unref(JOURS), (j, k) => {
                    return __hote$2.openBlock(), __hote$2.createElementBlock("span", {
                      key: k,
                      style: __hote$2.normalizeStyle(jour(l.a.jours & 1 << k))
                    }, __hote$2.toDisplayString(j), 5);
                  }), 128))
                ], 8, _hoisted_6$2))
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle({ ...zone("quoi"), display: "flex", flexDirection: "column", gap: "2px", minWidth: 0, color: estInactive(l) ? "var(--color-ink-faint)" : void 0 })
              }, [
                __hote$2.createElementVNode("span", _hoisted_7$1, __hote$2.toDisplayString(l.quoi[0]), 1),
                __hote$2.createElementVNode("span", _hoisted_8$1, __hote$2.toDisplayString(l.quoi[1]) + " · " + __hote$2.toDisplayString(__hote$2.unref(db)(l.a.volume_depart_db)) + " → " + __hote$2.toDisplayString(__hote$2.unref(db)(l.a.volume_cible_db)) + " " + __hote$2.toDisplayString(l.a.montee_s ? `en ${__hote$2.unref(duree)(l.a.montee_s)}` : "d'emblée") + " · " + __hote$2.toDisplayString(__hote$2.unref(fin)(l.a)), 1)
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle(etatStyle.value)
              }, [
                l.test ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                  t.value.etat === "en_attente" ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "accent",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [
                        __hote$2.createTextVNode(__hote$2.toDisplayString(reste.value ? `part dans ${reste.value} s` : "échéance passée, on attend…"), 1)
                      ]),
                      _: 1
                    }),
                    __hote$2.createElementVNode("span", { style: petit }, [
                      _cache[9] || (_cache[9] = __hote$2.createTextVNode("à ", -1)),
                      __hote$2.createElementVNode("b", _hoisted_9$1, __hote$2.toDisplayString(t.value.heure), 1),
                      __hote$2.createTextVNode(" (" + __hote$2.toDisplayString(__hote$2.unref(etat).fuseau) + ")", 1)
                    ])
                  ], 64)) : t.value.etat === "partie" ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "success",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [
                        __hote$2.createTextVNode("partie à " + __hote$2.toDisplayString(heureDepart.value), 1)
                      ]),
                      _: 1
                    }),
                    __hote$2.createElementVNode("span", { style: petit }, "avec " + __hote$2.toDisplayString(__hote$2.unref(virgule)((t.value.retardMs || 0) / 1e3)) + " s de retard" + __hote$2.toDisplayString(suite.value ? ` · ${suite.value}` : ""), 1)
                  ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 2 }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: "danger",
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [..._cache[10] || (_cache[10] = [
                        __hote$2.createTextVNode("pas partie", -1)
                      ])]),
                      _: 1
                    }),
                    __hote$2.createElementVNode("span", { style: petit }, "attendue à " + __hote$2.toDisplayString(t.value.heure) + ", rien à " + __hote$2.toDisplayString(heurePlus10.value), 1)
                  ], 64))
                ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                  __hote$2.createElementVNode("span", { style: petit }, [
                    l.a.prochaine ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                      _cache[11] || (_cache[11] = __hote$2.createTextVNode("Prochaine : ", -1)),
                      __hote$2.createElementVNode("b", _hoisted_10$1, __hote$2.toDisplayString(__hote$2.unref(quand)(l.a.prochaine, __hote$2.unref(etat).fuseau)), 1)
                    ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                      __hote$2.createTextVNode(__hote$2.toDisplayString(l.a.jours === 0 && l.a.derniere_echeance ? "Passée, désactivée" : "Désactivée"), 1)
                    ], 64))
                  ]),
                  __hote$2.createElementVNode("span", {
                    title: __hote$2.unref(AIDE_RESULTAT)[l.a.dernier_resultat] || "",
                    style: { "display": "inline-flex", "flex-wrap": "wrap", "gap": "var(--space-1-5)", "align-items": "center" }
                  }, [
                    __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                      tone: __hote$2.unref(resultat)(l.a.dernier_resultat).ton,
                      dot: ""
                    }, {
                      default: __hote$2.withCtx(() => [
                        __hote$2.createTextVNode(__hote$2.toDisplayString(__hote$2.unref(resultat)(l.a.dernier_resultat).lib), 1)
                      ]),
                      _: 2
                    }, 1032, ["tone"]),
                    l.a.derniere_echeance && l.a.dernier_resultat ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_12, __hote$2.toDisplayString(__hote$2.unref(quand)(l.a.derniere_echeance, __hote$2.unref(etat).fuseau)), 1)) : __hote$2.createCommentVNode("", true)
                  ], 8, _hoisted_11)
                ], 64))
              ], 4),
              __hote$2.createElementVNode("div", {
                style: __hote$2.normalizeStyle({ ...zone("act"), display: "flex", gap: "var(--space-1)", alignItems: "center", justifyContent: "flex-end" })
              }, [
                l.test ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiButton), {
                  key: 0,
                  intent: "ghost",
                  size: "sm",
                  onClick: __hote$2.unref(retirerTest)
                }, {
                  default: __hote$2.withCtx(() => [..._cache[12] || (_cache[12] = [
                    __hote$2.createTextVNode("Retirer", -1)
                  ])]),
                  _: 1
                }, 8, ["onClick"])) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
                  __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                    intent: "secondary",
                    size: "sm",
                    loading: essai.value === l.a.id,
                    "icon-only": __props.etroit,
                    label: `Essayer « ${l.a.nom} » maintenant`,
                    "aria-label": `Essayer « ${l.a.nom} » maintenant`,
                    onClick: ($event) => essayer(l.a)
                  }, {
                    leading: __hote$2.withCtx(() => [
                      __hote$2.createVNode(_sfc_main$6, { nom: "play" })
                    ]),
                    default: __hote$2.withCtx(() => [
                      !__props.etroit ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                        __hote$2.createTextVNode("Essayer maintenant")
                      ], 64)) : __hote$2.createCommentVNode("", true)
                    ]),
                    _: 1
                  }, 8, ["loading", "icon-only", "label", "aria-label", "onClick"]),
                  __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                    intent: "ghost",
                    size: "sm",
                    "icon-only": "",
                    label: `Modifier « ${l.a.nom} »`,
                    onClick: ($event) => emit("modifier", l.a.id)
                  }, {
                    leading: __hote$2.withCtx(() => [
                      __hote$2.createVNode(_sfc_main$6, { nom: "edit" })
                    ]),
                    _: 1
                  }, 8, ["label", "onClick"]),
                  __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                    intent: "ghost",
                    size: "sm",
                    "icon-only": "",
                    label: `Supprimer « ${l.a.nom} »`,
                    onClick: ($event) => aSupprimer.value = l.a.id
                  }, {
                    leading: __hote$2.withCtx(() => [
                      __hote$2.createVNode(_sfc_main$6, { nom: "trash" })
                    ]),
                    _: 1
                  }, 8, ["label", "onClick"])
                ], 64))
              ], 4),
              !l.test && aSupprimer.value === l.a.id ? (__hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_13, [
                __hote$2.createElementVNode("span", _hoisted_14, "Supprimer l'alarme « " + __hote$2.toDisplayString(l.a.nom) + " » ? Elle ne sonnera plus.", 1),
                __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                  intent: "ghost",
                  size: "sm",
                  onClick: _cache[3] || (_cache[3] = ($event) => aSupprimer.value = null)
                }, {
                  default: __hote$2.withCtx(() => [..._cache[13] || (_cache[13] = [
                    __hote$2.createTextVNode("Annuler", -1)
                  ])]),
                  _: 1
                }),
                __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                  intent: "danger",
                  size: "sm",
                  loading: enCours[l.a.id],
                  onClick: ($event) => supprimer(l.a)
                }, {
                  leading: __hote$2.withCtx(() => [
                    __hote$2.createVNode(_sfc_main$6, { nom: "trash" })
                  ]),
                  default: __hote$2.withCtx(() => [
                    _cache[14] || (_cache[14] = __hote$2.createTextVNode("Supprimer", -1))
                  ]),
                  _: 1
                }, 8, ["loading", "onClick"])
              ])) : __hote$2.createCommentVNode("", true),
              !l.test && retours[l.a.id] ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
                key: 1,
                ton: "danger",
                role: "alert",
                style: { "grid-column": "1 / -1" }
              }, {
                default: __hote$2.withCtx(() => [
                  __hote$2.createElementVNode("b", null, __hote$2.toDisplayString(retours[l.a.id].titre), 1),
                  __hote$2.createElementVNode("span", null, [
                    __hote$2.createTextVNode(__hote$2.toDisplayString(retours[l.a.id].texte) + " ", 1),
                    retours[l.a.id].reglage ? (__hote$2.openBlock(), __hote$2.createElementBlock("a", {
                      key: 0,
                      href: retours[l.a.id].reglage,
                      style: { "color": "inherit", "font-weight": "600" }
                    }, "Régler dans Réglages › Réseau", 8, _hoisted_15)) : retours[l.a.id].diagnostic ? (__hote$2.openBlock(), __hote$2.createElementBlock("a", {
                      key: 1,
                      href: "#",
                      style: { "color": "inherit", "font-weight": "600" },
                      onClick: _cache[4] || (_cache[4] = __hote$2.withModifiers(($event) => emit("diagnostic"), ["prevent"]))
                    }, "Voir le diagnostic")) : __hote$2.createCommentVNode("", true)
                  ])
                ]),
                _: 2
              }, 1024)) : __hote$2.createCommentVNode("", true)
            ], 12, _hoisted_2$2);
          }), 128))
        ]),
        __hote$2.createElementVNode("div", _hoisted_16, [
          __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(actives.value) + " alarme" + __hote$2.toDisplayString(actives.value > 1 ? "s" : "") + " active" + __hote$2.toDisplayString(actives.value > 1 ? "s" : "") + " · heures en " + __hote$2.toDisplayString(__hote$2.unref(etat).fuseau), 1),
          _cache[15] || (_cache[15] = __hote$2.createElementVNode("span", null, "Si unisson redémarre moins de 10 min après l'heure, l'alarme part en retard ; au-delà, elle est manquée.", -1))
        ])
      ], 64));
    };
  }
};
const _hoisted_1$1 = ["src"];
const _hoisted_2$1 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-1) var(--space-4)", "font-size": "var(--text-xs)", "color": "var(--color-ink-muted)", "margin-top": "var(--space-1)", "align-items": "center" } };
const _hoisted_3$1 = { style: { "display": "flex", "align-items": "center", "gap": "var(--space-2)" } };
const _hoisted_4$1 = {
  "aria-hidden": "true",
  style: { "width": "96px", "height": "4px", "border-radius": "2px", "background": "var(--color-surface-sunken)", "overflow": "hidden" }
};
const _hoisted_5$1 = { key: 0 };
const _hoisted_6$1 = { key: 1 };
const _hoisted_7 = { style: { "color": "var(--color-ink)", "font-family": "var(--font-mono)" } };
const _hoisted_8 = { key: 2 };
const _hoisted_9 = { style: { "display": "inline-flex", "align-items": "center", "gap": "var(--space-1)" } };
const _hoisted_10 = { key: 0 };
const _sfc_main$1 = {
  __name: "Seance",
  props: { annonce: { type: Object, default: null }, etroit: Boolean, arret: Boolean, erreurArret: { type: String, default: "" } },
  emits: ["arreter", "fermer", "diagnostic"],
  setup(__props, { emit: __emit }) {
    const props = __props;
    const emit = __emit;
    const s = __hote$2.computed(() => etat.seance);
    const genre = __hote$2.computed(() => etat.test && s.value && etat.test.id === s.value.alarme.id ? "Test" : "Réveil");
    const pochetteKo = __hote$2.ref(false);
    __hote$2.watch(() => {
      var _a, _b;
      return (_b = (_a = s.value) == null ? void 0 : _a.piste) == null ? void 0 : _b.id;
    }, () => {
      pochetteKo.value = false;
    });
    const degrade = __hote$2.computed(() => {
      var _a, _b;
      const h = (((_b = (_a = s.value) == null ? void 0 : _a.piste) == null ? void 0 : _b.id) || 7) * 47 % 360;
      return `linear-gradient(135deg, oklch(0.62 0.11 ${h}), oklch(0.32 0.07 ${h + 40}))`;
    });
    const pct = __hote$2.computed(() => {
      const x = s.value;
      if (!x) return 0;
      if (x.montee !== "en_cours") return 100;
      const plage = x.volume_cible - x.volume_depart;
      if (!plage || x.volume == null) return 0;
      return Math.max(0, Math.min(100, Math.round((x.volume - x.volume_depart) / plage * 100)));
    });
    const finTexte = __hote$2.computed(() => {
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
      aucun_format_commun: ["Aucun format lisible", "Aucune piste n'est dans un format que l'ampli lit. L'ampli n'a pas été allumé."]
    };
    const echec = __hote$2.computed(() => {
      const a = props.annonce;
      const [titre2, texte] = ECHECS[a == null ? void 0 : a.code] || ["La séance n'a pas pu jouer", (a == null ? void 0 : a.message) || (a == null ? void 0 : a.code) || ""];
      return { titre: titre2, texte };
    });
    const cadre = (ton) => ({
      display: "grid",
      gridTemplateColumns: props.etroit ? "auto 1fr" : "auto 1fr auto",
      gap: "var(--space-4)",
      alignItems: "center",
      padding: "var(--space-4)",
      background: "var(--color-surface)",
      border: `1px solid var(--color-${ton})`,
      borderRadius: "var(--radius-lg)",
      boxShadow: "var(--shadow-md)",
      marginBottom: "var(--space-6)"
    });
    const anneau = (ton) => ({
      width: "72px",
      height: "72px",
      borderRadius: "var(--radius-md)",
      background: "var(--color-surface-sunken)",
      display: "grid",
      placeItems: "center",
      color: ton === "danger" ? "var(--color-danger)" : "var(--color-ink-faint)"
    });
    const pochette = { width: "72px", height: "72px", borderRadius: "var(--radius-md)", boxShadow: "var(--shadow-cover)", objectFit: "cover", flex: "0 0 auto" };
    const milieu = { minWidth: 0, display: "flex", flexDirection: "column", gap: "var(--space-1)" };
    const eyebrow = { fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--color-ink-muted)" };
    const titre = { fontWeight: 600, fontSize: "var(--text-base)" };
    const sous = { color: "var(--color-ink-muted)" };
    const finStyle = __hote$2.computed(() => props.etroit ? { gridColumn: "1 / -1" } : {});
    return (_ctx, _cache) => {
      var _a, _b, _c, _d;
      return !s.value && __props.annonce && __props.annonce.type === "arretee" ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
        key: 0,
        ton: "info",
        style: { "margin-bottom": "var(--space-6)" }
      }, {
        actions: __hote$2.withCtx(() => [
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "ghost",
            size: "sm",
            onClick: _cache[0] || (_cache[0] = ($event) => emit("fermer"))
          }, {
            default: __hote$2.withCtx(() => [..._cache[6] || (_cache[6] = [
              __hote$2.createTextVNode("Fermer", -1)
            ])]),
            _: 1
          })
        ]),
        default: __hote$2.withCtx(() => [
          __hote$2.createElementVNode("span", null, "Séance « " + __hote$2.toDisplayString(__props.annonce.nom) + " » arrêtée. L'ampli reste allumé, sur sa source réseau.", 1)
        ]),
        _: 1
      })) : !s.value && __props.annonce && __props.annonce.type === "echec" ? (__hote$2.openBlock(), __hote$2.createElementBlock("section", {
        key: 1,
        "aria-label": "Séance",
        style: __hote$2.normalizeStyle(cadre("danger"))
      }, [
        __hote$2.createElementVNode("div", {
          style: __hote$2.normalizeStyle(anneau("danger"))
        }, [
          __hote$2.createVNode(_sfc_main$6, {
            nom: "alert",
            taille: "1.6em"
          })
        ], 4),
        __hote$2.createElementVNode("div", { style: milieu }, [
          __hote$2.createElementVNode("span", { style: eyebrow }, "Réveil « " + __hote$2.toDisplayString(__props.annonce.nom) + " »", 1),
          __hote$2.createElementVNode("span", { style: titre }, __hote$2.toDisplayString(echec.value.titre), 1),
          __hote$2.createElementVNode("span", { style: sous }, __hote$2.toDisplayString(echec.value.texte), 1)
        ]),
        __hote$2.createElementVNode("div", {
          style: __hote$2.normalizeStyle([finStyle.value, { "display": "flex", "gap": "var(--space-2)", "flex-wrap": "wrap" }])
        }, [
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "secondary",
            size: "md",
            block: __props.etroit,
            onClick: _cache[1] || (_cache[1] = ($event) => emit("diagnostic"))
          }, {
            default: __hote$2.withCtx(() => [..._cache[7] || (_cache[7] = [
              __hote$2.createTextVNode("Voir le diagnostic", -1)
            ])]),
            _: 1
          }, 8, ["block"]),
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "ghost",
            size: "md",
            block: __props.etroit,
            onClick: _cache[2] || (_cache[2] = ($event) => emit("fermer"))
          }, {
            default: __hote$2.withCtx(() => [..._cache[8] || (_cache[8] = [
              __hote$2.createTextVNode("Fermer", -1)
            ])]),
            _: 1
          }, 8, ["block"])
        ], 4)
      ], 4)) : s.value && s.value.etat !== "lecture" ? (__hote$2.openBlock(), __hote$2.createElementBlock("section", {
        key: 2,
        "aria-label": "Séance en cours",
        "aria-live": "polite",
        style: __hote$2.normalizeStyle(cadre("primary"))
      }, [
        __hote$2.createElementVNode("div", {
          style: __hote$2.normalizeStyle(anneau("faint"))
        }, [
          __hote$2.createVNode(__hote$2.unref(__hote.UiSpinner), { size: "md" })
        ], 4),
        __hote$2.createElementVNode("div", { style: milieu }, [
          __hote$2.createElementVNode("span", { style: eyebrow }, __hote$2.toDisplayString(genre.value) + " « " + __hote$2.toDisplayString(s.value.alarme.nom) + " » · démarrage", 1),
          __hote$2.createElementVNode("span", { style: titre }, __hote$2.toDisplayString(s.value.etat === "preparation" ? "Préparation de la séance…" : "Allumage de l'ampli…"), 1),
          __hote$2.createElementVNode("span", { style: sous }, __hote$2.toDisplayString(s.value.etat === "preparation" ? "Vérification du lien, du lecteur et des pistes, avant d'allumer l'ampli." : `Sortie de veille, volume à ${__hote$2.unref(db)(s.value.volume_depart)}, puis lecture (3 essais au plus).`), 1)
        ]),
        __hote$2.createElementVNode("div", {
          style: __hote$2.normalizeStyle(finStyle.value)
        }, [
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "danger",
            size: "md",
            block: __props.etroit,
            loading: __props.arret,
            onClick: _cache[3] || (_cache[3] = ($event) => emit("arreter"))
          }, {
            leading: __hote$2.withCtx(() => [
              __hote$2.createVNode(_sfc_main$6, { nom: "stop" })
            ]),
            default: __hote$2.withCtx(() => [
              _cache[9] || (_cache[9] = __hote$2.createTextVNode("Arrêter ", -1))
            ]),
            _: 1
          }, 8, ["block", "loading"])
        ], 4),
        __props.erreurArret ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
          key: 0,
          ton: "danger",
          role: "alert",
          style: { "grid-column": "1 / -1" }
        }, {
          default: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(__props.erreurArret), 1)
          ]),
          _: 1
        })) : __hote$2.createCommentVNode("", true)
      ], 4)) : s.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("section", {
        key: 3,
        "aria-label": "Séance en cours",
        "aria-live": "polite",
        style: __hote$2.normalizeStyle(cadre("primary"))
      }, [
        ((_a = s.value.piste) == null ? void 0 : _a.pochette) && !pochetteKo.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("img", {
          key: 0,
          src: s.value.piste.pochette,
          alt: "",
          style: pochette,
          onError: _cache[4] || (_cache[4] = ($event) => pochetteKo.value = true)
        }, null, 40, _hoisted_1$1)) : (__hote$2.openBlock(), __hote$2.createElementBlock("div", {
          key: 1,
          style: __hote$2.normalizeStyle({ ...pochette, background: degrade.value }),
          "aria-hidden": "true"
        }, null, 4)),
        __hote$2.createElementVNode("div", { style: milieu }, [
          __hote$2.createElementVNode("span", { style: eyebrow }, __hote$2.toDisplayString(genre.value) + " « " + __hote$2.toDisplayString(s.value.alarme.nom) + " » · en cours", 1),
          __hote$2.createElementVNode("span", {
            style: __hote$2.normalizeStyle({ ...titre, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" })
          }, __hote$2.toDisplayString(((_b = s.value.piste) == null ? void 0 : _b.titre) || "Lecture en cours"), 5),
          __hote$2.createElementVNode("span", {
            style: __hote$2.normalizeStyle({ ...sous, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" })
          }, __hote$2.toDisplayString([(_c = s.value.piste) == null ? void 0 : _c.artiste, (_d = s.value.piste) == null ? void 0 : _d.album].filter(Boolean).join(" · ")), 5),
          __hote$2.createElementVNode("div", _hoisted_2$1, [
            __hote$2.createElementVNode("span", _hoisted_3$1, [
              __hote$2.createElementVNode("span", _hoisted_4$1, [
                __hote$2.createElementVNode("span", {
                  style: __hote$2.normalizeStyle({ display: "block", height: "100%", background: "var(--color-primary)", width: `${pct.value}%`, transition: "width .5s linear" })
                }, null, 4)
              ]),
              s.value.montee === "interrompue" ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_5$1, [
                __hote$2.createTextVNode("Volume " + __hote$2.toDisplayString(__hote$2.unref(db)(s.value.volume)) + " · ", 1),
                _cache[10] || (_cache[10] = __hote$2.createElementVNode("b", { style: { "color": "var(--color-ink)" } }, "montée interrompue", -1)),
                _cache[11] || (_cache[11] = __hote$2.createTextVNode(", réglé à la main", -1))
              ])) : s.value.montee === "en_cours" ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_6$1, [
                _cache[12] || (_cache[12] = __hote$2.createTextVNode("Volume ", -1)),
                __hote$2.createElementVNode("b", _hoisted_7, __hote$2.toDisplayString(__hote$2.unref(db)(s.value.volume)), 1),
                __hote$2.createTextVNode(" → " + __hote$2.toDisplayString(__hote$2.unref(db)(s.value.volume_cible)), 1)
              ])) : (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_8, "Volume " + __hote$2.toDisplayString(__hote$2.unref(db)(s.value.volume ?? s.value.volume_cible)) + ", atteint", 1))
            ]),
            __hote$2.createElementVNode("span", _hoisted_9, [
              __hote$2.createVNode(_sfc_main$6, { nom: "clock" }),
              __hote$2.createTextVNode(" " + __hote$2.toDisplayString(finTexte.value), 1)
            ]),
            s.value.relances ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_10, "Relancée " + __hote$2.toDisplayString(s.value.relances) + " fois : l'ampli a lâché la lecture", 1)) : __hote$2.createCommentVNode("", true)
          ])
        ]),
        __hote$2.createElementVNode("div", {
          style: __hote$2.normalizeStyle(finStyle.value)
        }, [
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "danger",
            size: "md",
            block: __props.etroit,
            loading: __props.arret,
            onClick: _cache[5] || (_cache[5] = ($event) => emit("arreter"))
          }, {
            leading: __hote$2.withCtx(() => [
              __hote$2.createVNode(_sfc_main$6, { nom: "stop" })
            ]),
            default: __hote$2.withCtx(() => [
              _cache[13] || (_cache[13] = __hote$2.createTextVNode("Arrêter ", -1))
            ]),
            _: 1
          }, 8, ["block", "loading"])
        ], 4),
        __props.erreurArret ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$5, {
          key: 2,
          ton: "danger",
          role: "alert",
          style: { "grid-column": "1 / -1" }
        }, {
          default: __hote$2.withCtx(() => [
            __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(__props.erreurArret), 1)
          ]),
          _: 1
        })) : __hote$2.createCommentVNode("", true)
      ], 4)) : __hote$2.createCommentVNode("", true);
    };
  }
};
const _hoisted_1 = {
  "aria-label": "Fil d'Ariane",
  style: { "display": "flex", "gap": "var(--space-1-5)", "font-size": "var(--text-xs)", "color": "var(--color-ink-faint)", "margin-bottom": "var(--space-2)", "flex-wrap": "wrap" }
};
const _hoisted_2 = { style: { "display": "flex", "flex-wrap": "wrap", "align-items": "flex-end", "justify-content": "space-between", "gap": "var(--space-4)", "margin-bottom": "var(--space-6)" } };
const _hoisted_3 = ["aria-selected", "tabindex", "onClick", "onKeydown"];
const _hoisted_4 = {
  key: 1,
  "aria-label": "à vérifier",
  role: "img",
  style: { "width": "7px", "height": "7px", "border-radius": "50%", "background": "var(--color-danger)" }
};
const _hoisted_5 = {
  key: 2,
  "aria-hidden": "true",
  style: { "position": "absolute", "left": "0", "right": "0", "bottom": "0", "height": "2px", "background": "var(--color-primary)", "border-radius": "2px 2px 0 0" }
};
const _hoisted_6 = { role: "tabpanel" };
const _sfc_main = {
  __name: "Page",
  setup(__props) {
    const route = __hote$1.useRoute();
    const router = __hote$1.useRouter();
    const racine = __hote$2.ref(null);
    const etroit = __hote$2.ref(false);
    let observateur = null;
    const vue = __hote$2.computed(() => {
      const a = route.query.alarme;
      if (a === "nouvelle") return "nouvelle";
      return a && /^\d+$/.test(String(a)) ? "modifier" : "liste";
    });
    const idEdite = __hote$2.computed(() => Number(route.query.alarme));
    const onglet = __hote$2.ref(route.query.onglet === "diagnostic" ? "diagnostic" : "alarmes");
    __hote$2.watch(onglet, (o) => {
      if (o === "diagnostic") chargerDiagnostic();
      router.replace({ query: o === "diagnostic" ? { onglet: o } : {} });
    });
    function nouvelle() {
      router.push({ query: { alarme: "nouvelle" } });
      window.scrollTo(0, 0);
    }
    function modifier(id) {
      router.push({ query: { alarme: String(id) } });
      window.scrollTo(0, 0);
    }
    function revenir() {
      router.push({ query: {} });
      onglet.value = "alarmes";
    }
    const onglets = [{ v: "alarmes", lib: "Alarmes" }, { v: "diagnostic", lib: "Diagnostic" }];
    function clavierOnglets(e, i) {
      var _a, _b;
      const n = onglets.length;
      const cible = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
      if (cible === void 0) return;
      e.preventDefault();
      onglet.value = onglets[cible].v;
      const boutons = (_a = e.currentTarget.parentElement) == null ? void 0 : _a.querySelectorAll('[role="tab"]');
      (_b = boutons == null ? void 0 : boutons[cible]) == null ? void 0 : _b.focus();
    }
    const nbAlarmes = __hote$2.computed(() => (etat.alarmes || []).filter((a) => !a.test).length);
    const aVerifier = __hote$2.computed(() => {
      void etat.maintenant;
      const d = etat.diagnostic;
      if (!d && !etat.erreurDiagnostic) return false;
      if (etat.erreurDiagnostic || !d.ok) return true;
      if (etat.decalageServeurMs == null) return false;
      const nav = fuseauNavigateur();
      return Math.abs((murale(serveurMaintenant(), etat.fuseau) - murale(/* @__PURE__ */ new Date(), nav)) / 1e3) > 60;
    });
    const ECHECS = ["ampli_injoignable", "lien_mort", "lecture_impossible", "adresse_reseau_non_reglee", "aucune_piste", "aucun_format_commun"];
    const annonce = __hote$2.ref(null);
    const arret = __hote$2.ref(false);
    let cleVue = void 0;
    const cle = (d) => {
      var _a;
      return d ? `${(_a = d.alarme) == null ? void 0 : _a.id}|${d.debut}|${d.resultat}` : "";
    };
    __hote$2.watch(() => etat.derniere, (d) => {
      var _a, _b;
      const k = cle(d);
      if (cleVue === void 0 || k === cleVue) return;
      cleVue = k;
      if (!d || etat.test && ((_a = d.alarme) == null ? void 0 : _a.id) === etat.test.id) return;
      if (refusEssai !== null && ((_b = d.alarme) == null ? void 0 : _b.id) === refusEssai) {
        refusEssai = null;
        return;
      }
      if (d.resultat === "arretee") annonce.value = { type: "arretee", nom: d.alarme.nom };
      else if (ECHECS.includes(d.resultat) || String(d.resultat).startsWith("erreur:")) {
        annonce.value = { type: "echec", nom: d.alarme.nom, code: d.resultat, message: d.message };
      }
    });
    let refusEssai = null;
    function essaye(a, erreur) {
      if (erreur) {
        refusEssai = a.id;
        return;
      }
      annonce.value = null;
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
    const erreurArret = __hote$2.ref("");
    async function arreter() {
      arret.value = true;
      erreurArret.value = "";
      try {
        await arreterSeance();
      } catch (e) {
        erreurArret.value = `L'arrêt a échoué : ${e.message}`;
        await chargerSeance({ force: true });
      } finally {
        arret.value = false;
      }
    }
    __hote$2.watch(() => {
      var _a;
      return (_a = etat.seance) == null ? void 0 : _a.debut;
    }, () => {
      erreurArret.value = "";
    });
    function fermerAnnonce() {
      annonce.value = null;
    }
    let seconde = null;
    let sonde = null;
    let tours = 0;
    function sonder() {
      tours += 1;
      if (etat.seance || tours % 5 === 0) chargerSeance();
      if (tours % 15 === 0 && vue.value === "liste") chargerAlarmes();
    }
    __hote$2.onMounted(() => {
      if (racine.value && typeof ResizeObserver !== "undefined") {
        observateur = new ResizeObserver(([e]) => {
          etroit.value = e.contentRect.width < 760;
        });
        observateur.observe(racine.value);
      }
      chargerAlarmes();
      chargerSeance({ force: true }).then(() => {
        cleVue = cle(etat.derniere);
      });
      chargerDiagnostic();
      reprendreSuiviTest();
      seconde = setInterval(battre, 1e3);
      sonde = setInterval(sonder, 2e3);
    });
    __hote$2.onBeforeUnmount(() => {
      observateur == null ? void 0 : observateur.disconnect();
      clearInterval(seconde);
      clearInterval(sonde);
      arreterSuiviTest();
    });
    const eyebrow = { fontSize: "var(--text-xs)", fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--color-ink-muted)" };
    const titreH1 = {
      fontFamily: "var(--font-display)",
      fontSize: "var(--text-3xl)",
      lineHeight: "var(--text-3xl-lh)",
      letterSpacing: "var(--text-3xl-ls)",
      fontWeight: 600,
      margin: "var(--space-1) 0 0"
    };
    const barre = { display: "flex", gap: "var(--space-4)", boxShadow: "inset 0 -1px 0 var(--color-border)", marginBottom: "var(--space-6)", overflowX: "auto", scrollbarWidth: "none" };
    const tab = (on) => ({
      position: "relative",
      appearance: "none",
      background: "transparent",
      border: 0,
      padding: "var(--space-2-5) 0",
      flexShrink: 0,
      font: "inherit",
      fontSize: "var(--text-sm)",
      fontWeight: on ? 600 : 500,
      color: on ? "var(--color-ink)" : "var(--color-ink-muted)",
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: "var(--space-1-5)",
      minHeight: "var(--touch-min)"
    });
    const compte = (on) => ({
      fontFamily: "var(--font-mono)",
      fontSize: "11px",
      color: on ? "var(--color-primary-ink)" : "var(--color-ink-faint)",
      background: on ? "var(--color-primary-soft)" : "var(--color-surface-sunken)",
      padding: "1px var(--space-1-5)",
      borderRadius: "var(--radius-full)",
      minWidth: "18px",
      textAlign: "center"
    });
    return (_ctx, _cache) => {
      var _a, _b, _c, _d;
      return __hote$2.openBlock(), __hote$2.createElementBlock("div", {
        ref_key: "racine",
        ref: racine,
        "data-test": "denon-reveil",
        style: { "max-width": "960px", "min-width": "0", "font-size": "var(--text-sm)", "line-height": "var(--text-sm-lh)" }
      }, [
        __hote$2.createElementVNode("nav", _hoisted_1, [
          __hote$2.createVNode(__hote$2.unref(__hote$1.RouterLink), {
            to: "/plugins",
            style: { "color": "inherit", "text-decoration": "none" }
          }, {
            default: __hote$2.withCtx(() => [..._cache[2] || (_cache[2] = [
              __hote$2.createTextVNode("Extensions", -1)
            ])]),
            _: 1
          }),
          _cache[3] || (_cache[3] = __hote$2.createElementVNode("span", null, "›", -1)),
          _cache[4] || (_cache[4] = __hote$2.createElementVNode("span", null, "Denon", -1)),
          _cache[5] || (_cache[5] = __hote$2.createElementVNode("span", null, "›", -1)),
          __hote$2.createElementVNode("span", null, __hote$2.toDisplayString(vue.value === "nouvelle" ? "Nouvelle alarme" : vue.value === "modifier" ? "Modifier" : "Réveil"), 1)
        ]),
        vue.value !== "liste" ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$3, {
          key: String(__hote$2.unref(route).query.alarme),
          id: vue.value === "modifier" ? idEdite.value : null,
          etroit: etroit.value,
          onRetour: revenir,
          onEnregistree: revenir
        }, null, 8, ["id", "etroit"])) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
          __hote$2.createElementVNode("div", _hoisted_2, [
            __hote$2.createElementVNode("div", null, [
              __hote$2.createElementVNode("span", { style: eyebrow }, "Denon · " + __hote$2.toDisplayString(((_c = (_b = (_a = __hote$2.unref(etat).diagnostic) == null ? void 0 : _a.pilote) == null ? void 0 : _b.libelle) == null ? void 0 : _c.replace(/^Denon /, "")) || "réveil"), 1),
              __hote$2.createElementVNode("h1", { style: titreH1 }, "Réveil"),
              _cache[6] || (_cache[6] = __hote$2.createElementVNode("p", { style: { "margin": "var(--space-2) 0 0", "color": "var(--color-ink-muted)", "max-width": "60ch" } }, " L'ampli s'allume à l'heure dite, sur une playlist ou un tirage de la bibliothèque, et le volume monte doucement. ", -1))
            ]),
            ((_d = __hote$2.unref(etat).alarmes) == null ? void 0 : _d.some((a) => !a.test)) ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
              key: 0,
              style: __hote$2.normalizeStyle({ display: "inline-flex", width: etroit.value ? "100%" : void 0 })
            }, [
              __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                intent: "primary",
                size: "md",
                block: etroit.value,
                onClick: nouvelle
              }, {
                leading: __hote$2.withCtx(() => [
                  __hote$2.createVNode(_sfc_main$6, { nom: "plus" })
                ]),
                default: __hote$2.withCtx(() => [
                  _cache[7] || (_cache[7] = __hote$2.createTextVNode("Nouvelle alarme", -1))
                ]),
                _: 1
              }, 8, ["block"])
            ], 4)) : __hote$2.createCommentVNode("", true)
          ]),
          __hote$2.createVNode(_sfc_main$1, {
            annonce: annonce.value,
            etroit: etroit.value,
            arret: arret.value,
            "erreur-arret": erreurArret.value,
            onArreter: arreter,
            onFermer: fermerAnnonce,
            onDiagnostic: _cache[0] || (_cache[0] = ($event) => onglet.value = "diagnostic")
          }, null, 8, ["annonce", "etroit", "arret", "erreur-arret"]),
          __hote$2.createElementVNode("div", {
            role: "tablist",
            "aria-label": "Réveil",
            style: barre
          }, [
            (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(onglets, (o, i) => {
              return __hote$2.createElementVNode("button", {
                key: o.v,
                type: "button",
                role: "tab",
                "aria-selected": onglet.value === o.v,
                tabindex: onglet.value === o.v ? 0 : -1,
                style: __hote$2.normalizeStyle(tab(onglet.value === o.v)),
                onClick: ($event) => onglet.value = o.v,
                onKeydown: ($event) => clavierOnglets($event, i)
              }, [
                __hote$2.createTextVNode(__hote$2.toDisplayString(o.lib) + " ", 1),
                o.v === "alarmes" ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", {
                  key: 0,
                  style: __hote$2.normalizeStyle(compte(onglet.value === o.v))
                }, __hote$2.toDisplayString(nbAlarmes.value), 5)) : __hote$2.createCommentVNode("", true),
                o.v === "diagnostic" && aVerifier.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_4)) : __hote$2.createCommentVNode("", true),
                onglet.value === o.v ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_5)) : __hote$2.createCommentVNode("", true)
              ], 44, _hoisted_3);
            }), 64))
          ]),
          __hote$2.createElementVNode("div", _hoisted_6, [
            onglet.value === "alarmes" ? (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$2, {
              key: 0,
              etroit: etroit.value,
              onNouvelle: nouvelle,
              onModifier: modifier,
              onDiagnostic: _cache[1] || (_cache[1] = ($event) => onglet.value = "diagnostic"),
              onEssaye: essaye
            }, null, 8, ["etroit"])) : (__hote$2.openBlock(), __hote$2.createBlock(_sfc_main$4, {
              key: 1,
              etroit: etroit.value
            }, null, 8, ["etroit"]))
          ])
        ], 64))
      ], 512);
    };
  }
};
function installer(hote2, enregistrer) {
  enregistrer.page({ chemin: "/reveil", libelle: "Réveil", icone: "◷", composant: _sfc_main });
}
export {
  installer
};
