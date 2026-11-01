// Les écrans du réveil dans l'admin : une page « Réveil » dans Extensions,
// avec les onglets Alarmes et Diagnostic, la séance en cours et le
// formulaire d'une alarme (prototype validé : `docs/proto-reveil.html`).
import Page from "./Page.vue";

export function installer(hote, enregistrer) {
  enregistrer.page({ chemin: "/reveil", libelle: "Réveil", icone: "◷", composant: Page });
}
