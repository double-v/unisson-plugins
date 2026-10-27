// Les écrans de la safeplace dans l'admin : une page (groupe Extensions), un
// badge et un bloc sur la fiche artiste, une carte « Signaler » dans son hub.
import Badge from "./Badge.vue";
import Bloc from "./Bloc.vue";
import Page from "./Page.vue";
import Signaler from "./Signaler.vue";

export function installer(hote, enregistrer) {
  enregistrer.page({ chemin: "/", libelle: "Safeplace", icone: "⚑", composant: Page });
  enregistrer.emplacement("fiche-artiste.entete", { composant: Badge });
  enregistrer.emplacement("fiche-artiste.blocs", { titre: "Signalement", composant: Bloc });
  enregistrer.emplacement("fiche-artiste.hub", {
    titre: "Signaler",
    description: "Signaler cet artiste, ou revoir son signalement.",
    ecran: Signaler,
  });
}
