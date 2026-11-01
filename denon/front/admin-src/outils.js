// Les petites mises en forme du réveil : volumes, durées, jours, heures dans
// le fuseau du serveur, et les libellés des résultats. Rien ici ne parle à
// l'API : `api.js` s'en charge.

export const JOURS = ["L", "M", "M", "J", "V", "S", "D"];
export const JOURS_LONGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
// Les formats que propose le filtre de l'aléatoire du player, sans le WMA,
// que le tirage écarte (`_UNPLAYABLE_FORMATS` du cœur).
export const FORMATS = ["FLAC", "MP3", "M4A", "OGG", "WAV"];
export const PRESETS_MONTEE = [0, 120, 300, 600, 900];
export const FUSEAUX = ["Europe/Paris", "Europe/Brussels", "Europe/London", "UTC", "America/Montreal", "Indian/Reunion"];
// Au-delà, le volume cible est « fort pour un réveil » (choix de l'opérateur).
export const SEUIL_FORT_DB = -15;

const pad = (n) => String(n).padStart(2, "0");

/** −32 dB, −32,5 dB, +2 dB : le signe moins typographique, la virgule. */
export function db(v) {
  if (v == null || Number.isNaN(+v)) return "—";
  const n = +v;
  const signe = n < 0 ? "−" : n > 0 ? "+" : "";
  return `${signe}${Math.abs(n).toFixed(1).replace(".", ",").replace(",0", "")} dB`;
}

export function duree(s) {
  if (s === 0) return "d'emblée";
  if (s >= 3600) return "1 h";
  if (s < 60) return `${s} s`;
  return s % 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s / 60} min`;
}

/** `07:00` → `7:00` ; `07:42:15` → `7:42:15`. */
export function hm(heure) {
  if (!heure) return "—";
  const [h, ...reste] = heure.split(":");
  return [String(+h), ...reste].join(":");
}

export function libJours(j) {
  if (j === 0) return "une seule fois";
  if (j === 127) return "tous les jours";
  if (j === 31) return "en semaine";
  if (j === 96) return "le week-end";
  return JOURS_LONGS.filter((_, i) => j & (1 << i)).join(", ");
}

export function fin(a) {
  if (a.fin_mode === "duree") return `${a.fin_valeur} min puis veille`;
  if (a.fin_mode === "pistes") return `${a.fin_valeur} piste${a.fin_valeur > 1 ? "s" : ""} puis veille`;
  return "sans limite";
}

export function virgule(n, decimales = 1) {
  return Number(n).toFixed(decimales).replace(".", ",");
}

// ── les heures, dans un fuseau ────────────────────────────────────────────

function parties(date, fuseau) {
  const o = {};
  new Intl.DateTimeFormat("en-GB", {
    timeZone: fuseau, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", weekday: "short",
  }).formatToParts(date).forEach((p) => { o[p.type] = p.value; });
  return o;
}

/** L'heure murale d'un instant dans un fuseau, en millisecondes « comme si
 *  c'était de l'UTC » : deux heures murales se comparent par soustraction. */
export function murale(date, fuseau) {
  const o = parties(date, fuseau);
  return Date.UTC(+o.year, o.month - 1, +o.day, +o.hour, +o.minute, +o.second);
}

export function hms(date, fuseau) {
  const o = parties(date, fuseau);
  return `${o.hour}:${o.minute}:${o.second}`;
}

export function decalage(date, fuseau) {
  try {
    const n = new Intl.DateTimeFormat("en-US", { timeZone: fuseau, timeZoneName: "longOffset" })
      .formatToParts(date).find((p) => p.type === "timeZoneName").value;
    return n === "GMT" ? "+00:00" : n.replace("GMT", "");
  } catch {
    return "";
  }
}

export const fuseauNavigateur = () => Intl.DateTimeFormat().resolvedOptions().timeZone;

export function libEcart(s) {
  const a = Math.abs(Math.round(s));
  if (a < 2) return "moins de 1 s";
  const h = Math.floor(a / 3600), m = Math.floor((a % 3600) / 60), r = a % 60;
  return [h && `${h} h`, m && `${m} min`, r && !h && `${r} s`].filter(Boolean).join(" ");
}

const ISO_LOCAL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/;

/** Un instant ISO **rendu par le serveur dans son fuseau**
 *  (`2026-11-02T07:00:00.000+01:00`) : on lit sa date et son heure telles
 *  quelles, sans les reconvertir dans le fuseau du navigateur. */
function lireLocal(iso) {
  const m = ISO_LOCAL.exec(iso || "");
  return m ? { a: +m[1], mo: +m[2], j: +m[3], h: +m[4], mi: +m[5], s: +m[6] } : null;
}

const MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

/** « aujourd'hui 7:00 », « demain 7:00 », « lundi 7:00 », « 27 oct. 14:30 »,
 *  relatif au jour présent **dans le fuseau du serveur**. */
export function quand(iso, fuseau, maintenant = new Date()) {
  const l = lireLocal(iso);
  if (!l) return "";
  const o = parties(maintenant, fuseau);
  const jour = Date.UTC(l.a, l.mo - 1, l.j);
  const auj = Date.UTC(+o.year, o.month - 1, +o.day);
  const ecartJours = Math.round((jour - auj) / 86400000);
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

/** `HH:MM:SS` d'un instant ISO rendu dans le fuseau du serveur. */
export function heureDe(iso) {
  const l = lireLocal(iso);
  return l ? `${pad(l.h)}:${pad(l.mi)}:${pad(l.s)}` : "";
}

/** La prochaine occurrence d'une alarme en cours d'édition, calculée ici
 *  pour l'aperçu du formulaire (la liste, elle, lit celle du serveur). */
export function prochaineApercu(heure, jours, fuseau, maintenant = new Date()) {
  const m = /^(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(heure || "");
  if (!m) return null;
  const [h, mi, s] = [+m[1], +m[2], +(m[3] || 0)];
  const ici = murale(maintenant, fuseau);
  const minuit = ici - (ici % 86400000);
  for (let k = 0; k < 8; k++) {
    const t = minuit + k * 86400000 + ((h * 60 + mi) * 60 + s) * 1000;
    if (t <= ici) continue;
    const js = new Date(t).getUTCDay();
    const bit = js === 0 ? 64 : 1 << (js - 1);
    if (jours === 0 || jours & bit) {
      const lib = k === 0 ? "aujourd'hui" : k === 1 ? "demain" : JOURS_LONGS[(js + 6) % 7];
      return `${lib} ${h}:${pad(mi)}${s ? `:${pad(s)}` : ""}`;
    }
  }
  return null;
}

// ── les résultats ────────────────────────────────────────────────────────

export const RESULTATS = {
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
  jamais: { ton: "neutral", lib: "Pas encore partie" },
};

export function resultat(code) {
  if (!code) return RESULTATS.jamais;
  if (RESULTATS[code]) return RESULTATS[code];
  if (code.startsWith("erreur:")) return { ton: "danger", lib: "Erreur interne" };
  return { ton: "warning", lib: code.replaceAll("_", " ") };
}

export const AIDE_RESULTAT = {
  ampli_injoignable: "L'ampli n'a pas répondu. Voir le diagnostic.",
  adresse_reseau_non_reglee: "L'ampli ne sait pas où chercher la musique : réglez l'adresse réseau d'unisson.",
  manquee: "unisson était arrêté à l'heure prévue, et a redémarré plus de 10 min après.",
  aucune_piste: "Le contexte choisi n'a aucune piste jouable.",
  aucun_format_commun: "Aucune piste n'est dans un format que l'ampli lit, même convertie.",
  lecture_impossible: "L'ampli s'est allumé, mais n'est pas passé en lecture.",
};

/** Les formats d'un `GetProtocolInfo` (`http-get:*:audio/flac:*`), en noms
 *  courts, dans l'ordre et sans doublon. */
export function formatsCourts(protocoles) {
  const NOMS = {
    "audio/flac": "FLAC", "audio/x-flac": "FLAC",
    "audio/mpeg": "MP3", "audio/mp3": "MP3", "audio/x-mpeg": "MP3",
    "audio/mp4": "AAC", "audio/x-m4a": "AAC", "audio/aac": "AAC", "audio/x-aac": "AAC", "audio/m4a": "AAC",
    "audio/wav": "WAV", "audio/x-wav": "WAV", "audio/wave": "WAV",
    "audio/l16": "PCM", "audio/lpcm": "PCM",
    "audio/aiff": "AIFF", "audio/x-aiff": "AIFF",
    "audio/x-ms-wma": "WMA", "audio/wma": "WMA",
    "audio/ogg": "OGG", "audio/x-ogg": "OGG", "application/ogg": "OGG",
    "audio/x-alac": "ALAC", "audio/alac": "ALAC",
    "audio/dsd": "DSD", "audio/x-dsd": "DSD", "audio/x-dsf": "DSD", "audio/x-dff": "DSD",
  };
  const vus = [];
  for (const p of protocoles || []) {
    const mime = (String(p).split(":")[2] || "").split(";")[0].trim().toLowerCase();
    const nom = NOMS[mime] || (mime.startsWith("audio/") ? mime.slice(6).replace(/^x-/, "").toUpperCase() : null);
    if (nom && !vus.includes(nom)) vus.push(nom);
  }
  return vus;
}
