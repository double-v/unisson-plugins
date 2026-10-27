// Les écrans de la safeplace dans l'admin : une page (groupe Extensions), un
// badge et un bloc sur la fiche artiste, une carte « Signaler » dans son hub,
// et le détail de la carte que l'assistant propose dans le chat (#931).
import Badge from "./Badge.vue";
import Bloc from "./Bloc.vue";
import CarteChat from "./CarteChat.vue";
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
  enregistrer.emplacement("chat.carte-action", { composant: CarteChat });
}
