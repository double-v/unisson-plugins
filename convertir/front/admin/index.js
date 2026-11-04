const __hote$1 = globalThis.__unisson__.vue;
const hote = globalThis.__unisson__;
const deja = {};
const __hote = new Proxy({}, {
  get: (_, nom) => deja[nom] ?? (deja[nom] = hote.vue.defineAsyncComponent(() => hote.ds.charger().then((m) => m[nom])))
});
const _hoisted_1$1 = {
  "data-test": "convertir-apercu",
  style: { "display": "grid", "gap": "var(--space-3)" }
};
const _hoisted_2 = {
  key: 0,
  style: { "font-size": "0.875rem", "color": "var(--color-ink-muted)" }
};
const _hoisted_3 = {
  key: 1,
  role: "alert",
  style: { "font-size": "0.875rem" }
};
const _hoisted_4 = {
  key: 0,
  style: { "font-size": "0.875rem" }
};
const _hoisted_5 = { style: { "width": "100%", "font-size": "0.8125rem", "border-collapse": "collapse" } };
const _hoisted_6 = ["data-convertible"];
const _hoisted_7 = { style: { "padding": "var(--space-1)", "overflow-wrap": "anywhere" } };
const _hoisted_8 = { style: { "padding": "var(--space-1)", "overflow-wrap": "anywhere" } };
const _hoisted_9 = {
  key: 0,
  style: { "display": "block", "color": "var(--color-ink-muted)" }
};
const _hoisted_10 = {
  key: 1,
  style: { "color": "var(--color-ink-muted)" }
};
const _hoisted_11 = { style: { "padding": "var(--space-1)", "white-space": "nowrap" } };
const _hoisted_12 = {
  key: 0,
  style: { "font-size": "0.8125rem", "color": "var(--color-ink-muted)" }
};
const _hoisted_13 = {
  key: 1,
  role: "alert",
  style: { "font-size": "0.8125rem" }
};
const _hoisted_14 = {
  key: 2,
  role: "status",
  style: { "font-size": "0.8125rem" }
};
const _hoisted_15 = {
  key: 3,
  role: "alert",
  style: { "font-size": "0.8125rem" }
};
const _hoisted_16 = { key: 4 };
const _hoisted_17 = {
  key: 2,
  role: "status",
  style: { "font-size": "0.8125rem", "color": "var(--color-ink-muted)" }
};
const _sfc_main$1 = {
  __name: "Convertir",
  props: { album: { type: Object, required: true } },
  setup(__props) {
    const props = __props;
    const { api } = globalThis.__unisson__;
    const albumId = __hote$1.computed(() => props.album.album_id ?? props.album.id);
    const vue = __hote$1.ref(null);
    const chargement = __hote$1.ref(true);
    const erreur = __hote$1.ref("");
    const occupe = __hote$1.ref(false);
    const etat = __hote$1.ref("");
    const message = __hote$1.ref("");
    const nomDe = (chemin) => chemin.split("/").pop();
    function motifErreur(e) {
      var _a, _b;
      return ((_b = (_a = e == null ? void 0 : e.response) == null ? void 0 : _a.data) == null ? void 0 : _b.detail) || (e == null ? void 0 : e.message) || "La requête a échoué.";
    }
    async function tamponner() {
      occupe.value = true;
      message.value = "";
      try {
        const ops = await api.post("/operations/staged", [{
          operation_type: "convertir.mp3",
          source: "convertir",
          target_type: "album",
          target_id: albumId.value,
          params_json: { track_ids: vue.value.pistes.filter((p) => p.convertible).map((p) => p.track_id) }
        }]);
        const op = Array.isArray(ops) ? ops[0] : null;
        etat.value = (op == null ? void 0 : op.status) || "";
        if (op == null ? void 0 : op.deduplicated) {
          message.value = "Cette conversion attendait déjà au tampon : rien n'a été ajouté.";
        } else if ((op == null ? void 0 : op.status) === "pending") {
          message.value = "Au tampon : la conversion attend votre approbation dans « Opérations ».";
        } else {
          message.value = `État rendu : ${(op == null ? void 0 : op.status) || "inconnu"}${(op == null ? void 0 : op.reason) ? ` (${op.reason})` : ""}.`;
        }
      } catch (e) {
        message.value = motifErreur(e);
      } finally {
        occupe.value = false;
      }
    }
    __hote$1.onMounted(async () => {
      try {
        vue.value = await api.get(`/plugins/convertir/albums/${albumId.value}/apercu`);
      } catch (e) {
        erreur.value = motifErreur(e);
      } finally {
        chargement.value = false;
      }
    });
    return (_ctx, _cache) => {
      return __hote$1.openBlock(), __hote$1.createElementBlock("div", _hoisted_1$1, [
        chargement.value ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_2, "Lecture de l'album…")) : erreur.value ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_3, __hote$1.toDisplayString(erreur.value), 1)) : vue.value ? (__hote$1.openBlock(), __hote$1.createElementBlock(__hote$1.Fragment, { key: 2 }, [
          !vue.value.pistes.length ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_4, "Cet album n'a aucune piste WMA : rien à convertir.")) : (__hote$1.openBlock(), __hote$1.createElementBlock(__hote$1.Fragment, { key: 1 }, [
            _cache[1] || (_cache[1] = __hote$1.createElementVNode("p", { style: { "font-size": "0.875rem" } }, " Réencode les WMA en MP3 (CBR, au débit de la source ou au palier juste au-dessus) et recopie leurs tags en ID3v2.4. Les WMA partent à la corbeille ; favoris, playlists et écoutes suivent les pistes. La conversion se révoque depuis l'historique des opérations tant que l'album n'a pas été renommé ou déplacé. ", -1)),
            __hote$1.createElementVNode("table", _hoisted_5, [
              _cache[0] || (_cache[0] = __hote$1.createElementVNode("thead", null, [
                __hote$1.createElementVNode("tr", { style: { "text-align": "left", "color": "var(--color-ink-muted)" } }, [
                  __hote$1.createElementVNode("th", { style: { "padding": "var(--space-1)" } }, "Piste"),
                  __hote$1.createElementVNode("th", { style: { "padding": "var(--space-1)" } }, "Devient"),
                  __hote$1.createElementVNode("th", { style: { "padding": "var(--space-1)" } }, "Débit")
                ])
              ], -1)),
              __hote$1.createElementVNode("tbody", null, [
                (__hote$1.openBlock(true), __hote$1.createElementBlock(__hote$1.Fragment, null, __hote$1.renderList(vue.value.pistes, (p) => {
                  return __hote$1.openBlock(), __hote$1.createElementBlock("tr", {
                    key: p.track_id,
                    "data-convertible": p.convertible
                  }, [
                    __hote$1.createElementVNode("td", _hoisted_7, __hote$1.toDisplayString(nomDe(p.source)), 1),
                    __hote$1.createElementVNode("td", _hoisted_8, [
                      p.convertible ? (__hote$1.openBlock(), __hote$1.createElementBlock(__hote$1.Fragment, { key: 0 }, [
                        __hote$1.createTextVNode(__hote$1.toDisplayString(p.nom_cible) + " ", 1),
                        p.ecartes.length ? (__hote$1.openBlock(), __hote$1.createElementBlock("span", _hoisted_9, " non recopié : " + __hote$1.toDisplayString(p.ecartes.join(", ")), 1)) : __hote$1.createCommentVNode("", true)
                      ], 64)) : (__hote$1.openBlock(), __hote$1.createElementBlock("span", _hoisted_10, "gardée — " + __hote$1.toDisplayString(p.motif_libelle || p.motif), 1))
                    ]),
                    __hote$1.createElementVNode("td", _hoisted_11, [
                      p.convertible ? (__hote$1.openBlock(), __hote$1.createElementBlock(__hote$1.Fragment, { key: 0 }, [
                        __hote$1.createTextVNode(__hote$1.toDisplayString(p.debit_source || "?") + " → " + __hote$1.toDisplayString(p.debit_cible) + " kbps", 1)
                      ], 64)) : __hote$1.createCommentVNode("", true)
                    ])
                  ], 8, _hoisted_6);
                }), 128))
              ])
            ]),
            vue.value.a_convertir ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_12, " À la corbeille : " + __hote$1.toDisplayString(vue.value.corbeille.length) + " fichier" + __hote$1.toDisplayString(vue.value.corbeille.length > 1 ? "s" : "") + " WMA. ", 1)) : __hote$1.createCommentVNode("", true),
            !vue.value.ffmpeg ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_13, "ffmpeg est introuvable sur le serveur : la conversion ne peut pas tourner.")) : vue.value.scan_en_cours ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_14, " Un scan tourne : la conversion pourra attendre au tampon, elle ne s'appliquera qu'une fois le scan fini. ")) : !vue.value.mode_edition ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_15, " Le mode édition est coupé : la conversion peut attendre au tampon, elle ne s'appliquera qu'une fois activé. ")) : __hote$1.createCommentVNode("", true),
            vue.value.a_convertir ? (__hote$1.openBlock(), __hote$1.createElementBlock("div", _hoisted_16, [
              __hote$1.createVNode(__hote$1.unref(__hote.UiButton), {
                intent: "primary",
                size: "sm",
                loading: occupe.value,
                disabled: !vue.value.ffmpeg || !!etat.value,
                "data-test": "convertir-tamponner",
                onClick: tamponner
              }, {
                default: __hote$1.withCtx(() => [
                  __hote$1.createTextVNode(" Tamponner la conversion (" + __hote$1.toDisplayString(vue.value.a_convertir) + " piste" + __hote$1.toDisplayString(vue.value.a_convertir > 1 ? "s" : "") + ") ", 1)
                ]),
                _: 1
              }, 8, ["loading", "disabled"])
            ])) : __hote$1.createCommentVNode("", true)
          ], 64)),
          message.value ? (__hote$1.openBlock(), __hote$1.createElementBlock("p", _hoisted_17, __hote$1.toDisplayString(message.value), 1)) : __hote$1.createCommentVNode("", true)
        ], 64)) : __hote$1.createCommentVNode("", true)
      ]);
    };
  }
};
const _hoisted_1 = { "data-test": "convertir-outil" };
const _sfc_main = {
  __name: "OutilQualite",
  props: { album: { type: Object, required: true } },
  setup(__props) {
    const ouvert = __hote$1.ref(false);
    return (_ctx, _cache) => {
      return __hote$1.openBlock(), __hote$1.createElementBlock("span", _hoisted_1, [
        __hote$1.createVNode(__hote$1.unref(__hote.UiButton), {
          intent: "secondary",
          size: "sm",
          onClick: _cache[0] || (_cache[0] = ($event) => ouvert.value = true)
        }, {
          default: __hote$1.withCtx(() => [..._cache[2] || (_cache[2] = [
            __hote$1.createTextVNode("Convertir…", -1)
          ])]),
          _: 1
        }),
        __hote$1.createVNode(__hote$1.unref(__hote.UiModal), {
          modelValue: ouvert.value,
          "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => ouvert.value = $event),
          title: "Convertir en MP3",
          subtitle: __props.album.album_name,
          "test-id": "convertir-modale"
        }, {
          default: __hote$1.withCtx(() => [
            ouvert.value ? (__hote$1.openBlock(), __hote$1.createBlock(_sfc_main$1, {
              key: 0,
              album: __props.album
            }, null, 8, ["album"])) : __hote$1.createCommentVNode("", true)
          ]),
          _: 1
        }, 8, ["modelValue", "subtitle"])
      ]);
    };
  }
};
function installer(hote2, enregistrer) {
  enregistrer.emplacement("fiche-album.hub", {
    titre: "Convertir en MP3",
    description: "Rendre taguables les pistes WMA : MP3 au débit de la source (ou juste au-dessus), tags recopiés, WMA à la corbeille.",
    ecran: _sfc_main$1
  });
  enregistrer.emplacement("qualite.ligne", { titre: "Conversion", composant: _sfc_main });
}
export {
  installer
};
