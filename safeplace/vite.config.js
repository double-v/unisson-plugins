// Préréglage Vite d'un plugin unisson (spec 018, `contracts/emplacements-front.md`).
//
// Le plugin n'embarque ni Vue, ni vue-router, ni le design system : il les
// reçoit de l'hôte, `globalThis.__unisson__`. Ce préréglage réécrit leurs
// imports vers cet objet, si bien qu'un écran s'écrit en SFC ordinaire
// (`import { ref } from "vue"`, `import { UiButton } from "@ds/primitives"`)
// et se compile en un seul `front/admin/index.js`.
//
// Pas de `<style>` : la bibliothèque compilée n'injecte pas de feuille. Les
// écrans se font avec les primitives et, au besoin, des `style` sur les
// jetons (`var(--space-2)`, `var(--color-ink-muted)`) — une seule DA.
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const PREFIXE = "\0unisson-hote:";
const HOTE = {
  vue: "globalThis.__unisson__.vue",
  "vue-router": "globalThis.__unisson__.vueRouter",
};

// Les primitives arrivent à la demande (`ds.charger()`) : chacune devient un
// composant asynchrone, résolu au premier rendu.
const PRIMITIVES = `
const hote = globalThis.__unisson__;
const deja = {};
export const __hote = new Proxy({}, {
  get: (_, nom) => (deja[nom] ??= hote.vue.defineAsyncComponent(() => hote.ds.charger().then((m) => m[nom]))),
});
`;

export function hoteUnisson() {
  return {
    name: "unisson-hote",
    enforce: "pre",
    resolveId(id) {
      if (id === "@ds/fondations" || id.startsWith("@ds/fondations/")) {
        this.error("@ds/fondations est refusé : les jetons sont déjà dans la feuille de l'hôte.");
      }
      if (id in HOTE || id === "@ds/primitives") return PREFIXE + id;
      return null;
    },
    load(id) {
      if (!id.startsWith(PREFIXE)) return null;
      const nom = id.slice(PREFIXE.length);
      const code = nom === "@ds/primitives" ? PRIMITIVES : `export const __hote = ${HOTE[nom]};`;
      return { code, syntheticNamedExports: "__hote" };
    },
  };
}

export default defineConfig({
  plugins: [hoteUnisson(), vue()],
  build: {
    outDir: "front/admin",
    emptyOutDir: true,
    lib: { entry: "front/admin-src/index.js", formats: ["es"], fileName: () => "index.js" },
    minify: false,
  },
});
