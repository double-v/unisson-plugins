// Les écrans du plugin dans l'admin : une carte « Convertir en MP3 » dans le
// hub de la fiche album, et un outil au bout des lignes de la page qualité,
// qui ouvre le même aperçu dans une modale.
import Convertir from "./Convertir.vue";
import OutilQualite from "./OutilQualite.vue";

export function installer(hote, enregistrer) {
  enregistrer.emplacement("fiche-album.hub", {
    titre: "Convertir en MP3",
    description: "Rendre taguables les pistes WMA : MP3 au même débit, tags recopiés, WMA à la corbeille.",
    ecran: Convertir,
  });
  enregistrer.emplacement("qualite.ligne", { titre: "Conversion", composant: OutilQualite });
}
