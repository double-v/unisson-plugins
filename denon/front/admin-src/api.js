// Les appels du réveil, par l'API de l'hôte (`__unisson__.api`, axios de
// l'admin, base `/api`). Les erreurs sortent sous une seule forme :
// `{ statut, code, message, erreurs, reglage }`, avec les 422 de validation
// rangés par champ (`erreurs`).
const { api } = globalThis.__unisson__;

export const BASE = "/plugins/denon/reveil";

export class ErreurReveil extends Error {
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
  503: "Le plugin Denon ne répond pas (503).",
};

function normaliser(e) {
  const r = e?.response;
  if (!r) return new ErreurReveil({ message: "Le serveur ne répond pas. Vérifiez qu'unisson tourne." });
  const d = r.data && typeof r.data === "object" ? r.data : {};
  const message = typeof d.message === "string" ? d.message
    : typeof d.detail === "string" ? d.detail
      : MESSAGES[r.status] || `Réponse inattendue du serveur (${r.status}).`;
  return new ErreurReveil({
    statut: r.status,
    code: d.error || "",
    // Le motif du cœur (`detail`) dit quelle origine ou quel hôte est refusé.
    message: r.status === 403 ? `${MESSAGES[403]}${typeof d.detail === "string" ? ` ${d.detail}` : ""}` : message,
    erreurs: Array.isArray(d.erreurs) ? d.erreurs : [],
    reglage: d.reglage || null,
  });
}

const appel = (p) => p.catch((e) => { throw normaliser(e); });

export const reveil = {
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
  regler: (valeurs) => appel(api.put("/plugins/denon/settings", valeurs)),
};

// Les API du cœur que l'admin utilise déjà (playlists du player, genres,
// recherche d'artistes et d'albums).
export const coeur = {
  playlists: () => appel(api.get("/playlists", { limit: 500 })).then((p) => p.items || []),
  genres: () => appel(api.get("/genres")),
  artistes: (q) => appel(api.get("/artists", { search: q, limit: 8, with_stats: true })).then((p) => p.items || []),
  artiste: (id) => appel(api.get(`/artists/${id}`)),
  albums: (q) => appel(api.get("/albums/search", { q })).then((l) => (l || []).slice(0, 8)),
  album: (id) => appel(api.get(`/albums/${id}`)),
};

export const nomArtiste = (a) => a?.display_name || a?.name_from_nfo || a?.folder_name || a?.name || "";
export const nomAlbum = (a) => a?.name || a?.name_from_nfo || a?.name_from_tags || a?.name_from_folder || a?.folder_name || "";
