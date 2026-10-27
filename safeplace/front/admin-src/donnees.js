// Le signalement d'un artiste, lu une fois pour le badge et le bloc de la
// même fiche : deux contributions, une seule requête.
const { api } = globalThis.__unisson__;
const cache = new Map();

export const GRAVITES = { "condamné": "Condamné", "accusé": "Accusé", "autre": "Autre" };
export const PAR = { user: "Signalé par vous", serge: "Suggéré par l'assistant" };

export function signalement(artistId) {
  if (!cache.has(artistId)) cache.set(artistId, api.get(`/plugins/safeplace/flags/${artistId}`).catch(() => null));
  return cache.get(artistId);
}

export function oublier(artistId) {
  cache.delete(artistId);
}

export function dateCourte(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}
