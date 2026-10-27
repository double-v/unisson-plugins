const __hote$2 = globalThis.__unisson__.vue;
const __hote$1 = globalThis.__unisson__.vueRouter;
const { api } = globalThis.__unisson__;
const cache = /* @__PURE__ */ new Map();
const GRAVITES = { "condamné": "Condamné", "accusé": "Accusé", "autre": "Autre" };
const PAR = { user: "Signalé par vous", serge: "Suggéré par l'assistant" };
function signalement(artistId) {
  if (!cache.has(artistId)) cache.set(artistId, api.get(`/plugins/safeplace/flags/${artistId}`).catch(() => null));
  return cache.get(artistId);
}
function oublier(artistId) {
  cache.delete(artistId);
}
function dateCourte(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(void 0, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}
const _sfc_main$3 = {
  __name: "Badge",
  props: { artiste: { type: Object, required: true } },
  setup(__props) {
    const props = __props;
    const item = __hote$2.ref(null);
    __hote$2.onMounted(async () => {
      item.value = await signalement(props.artiste.id);
    });
    return (_ctx, _cache) => {
      return item.value && !item.value.pending_review ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote$1.RouterLink), {
        key: 0,
        to: "/p/safeplace/",
        "data-test": "safeplace-badge",
        style: { "display": "inline-flex", "align-items": "center", "gap": "var(--space-1)", "color": "var(--color-danger)", "text-decoration": "none", "font-size": "0.75rem", "font-weight": "600" }
      }, {
        default: __hote$2.withCtx(() => [..._cache[0] || (_cache[0] = [
          __hote$2.createElementVNode("span", { "aria-hidden": "true" }, "⚑", -1),
          __hote$2.createTextVNode(" Signalé", -1)
        ])]),
        _: 1
      })) : __hote$2.createCommentVNode("", true);
    };
  }
};
const _hoisted_1$2 = {
  key: 0,
  "data-test": "safeplace-bloc",
  style: { "display": "grid", "gap": "var(--space-1)", "font-size": "0.875rem" }
};
const _hoisted_2$2 = { key: 0 };
const _hoisted_3$2 = ["href"];
const _hoisted_4$2 = { style: { "color": "var(--color-ink-faint)" } };
const _sfc_main$2 = {
  __name: "Bloc",
  props: { artiste: { type: Object, required: true } },
  setup(__props) {
    const props = __props;
    const item = __hote$2.ref(null);
    __hote$2.onMounted(async () => {
      item.value = await signalement(props.artiste.id);
    });
    return (_ctx, _cache) => {
      return item.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_1$2, [
        __hote$2.createElementVNode("p", null, [
          _cache[0] || (_cache[0] = __hote$2.createElementVNode("strong", null, "Motif :", -1)),
          __hote$2.createTextVNode(" " + __hote$2.toDisplayString(item.value.reasons || "—"), 1)
        ]),
        __hote$2.createElementVNode("p", null, [
          _cache[1] || (_cache[1] = __hote$2.createElementVNode("strong", null, "Gravité :", -1)),
          __hote$2.createTextVNode(" " + __hote$2.toDisplayString(__hote$2.unref(GRAVITES)[item.value.severity] || item.value.severity), 1)
        ]),
        item.value.source_url ? (__hote$2.openBlock(), __hote$2.createElementBlock("p", _hoisted_2$2, [
          _cache[2] || (_cache[2] = __hote$2.createElementVNode("strong", null, "Source :", -1)),
          __hote$2.createElementVNode("a", {
            href: item.value.source_url,
            target: "_blank",
            rel: "noopener",
            style: { "text-decoration": "underline" }
          }, __hote$2.toDisplayString(item.value.source_url), 9, _hoisted_3$2)
        ])) : __hote$2.createCommentVNode("", true),
        __hote$2.createElementVNode("p", _hoisted_4$2, [
          __hote$2.createTextVNode(__hote$2.toDisplayString(__hote$2.unref(PAR)[item.value.flagged_by] || item.value.flagged_by), 1),
          item.value.pending_review ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
            __hote$2.createTextVNode(" · en attente de validation")
          ], 64)) : __hote$2.createCommentVNode("", true),
          __hote$2.createTextVNode(" · " + __hote$2.toDisplayString(__hote$2.unref(dateCourte)(item.value.flagged_at)), 1)
        ])
      ])) : __hote$2.createCommentVNode("", true);
    };
  }
};
const hote = globalThis.__unisson__;
const deja = {};
const __hote = new Proxy({}, {
  get: (_, nom) => deja[nom] ?? (deja[nom] = hote.vue.defineAsyncComponent(() => hote.ds.charger().then((m) => m[nom])))
});
const _hoisted_1$1 = {
  "data-test": "safeplace-page",
  style: { "display": "grid", "gap": "var(--space-4)" }
};
const _hoisted_2$1 = {
  key: 0,
  "data-test": "safeplace-en-attente",
  style: { "display": "grid", "gap": "var(--space-2)", "padding": "var(--space-3)", "border": "1px solid var(--color-border)", "border-radius": "var(--radius-lg)", "background": "var(--color-warning-soft)" }
};
const _hoisted_3$1 = { style: { "font-weight": "600" } };
const _hoisted_4$1 = { style: { "flex": "1", "min-width": "12rem", "font-size": "0.75rem", "color": "var(--color-ink-muted)" } };
const _hoisted_5$1 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-2)" } };
const _hoisted_6$1 = ["value"];
const _hoisted_7 = {
  key: 1,
  role: "status",
  style: { "font-size": "0.75rem", "color": "var(--color-ink-muted)" }
};
const _hoisted_8 = { style: { "display": "grid", "gap": "var(--space-2)" } };
const _hoisted_9 = { style: { "flex": "1", "min-width": "14rem", "display": "grid", "gap": "var(--space-1)" } };
const _hoisted_10 = { style: { "display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "var(--space-2)" } };
const _hoisted_11 = { style: { "font-size": "0.75rem", "color": "var(--color-ink-muted)" } };
const _hoisted_12 = {
  key: 0,
  style: { "font-size": "0.875rem" }
};
const _hoisted_13 = { style: { "font-size": "0.75rem", "color": "var(--color-ink-faint)" } };
const _hoisted_14 = ["href"];
const _hoisted_15 = { key: 3 };
const BASE = "/plugins/safeplace/flags";
const _sfc_main$1 = {
  __name: "Page",
  setup(__props) {
    const TON = { "condamné": "danger", "accusé": "warning", "autre": "neutral" };
    const { api: api2 } = globalThis.__unisson__;
    const items = __hote$2.ref([]);
    const total = __hote$2.ref(0);
    const enAttente = __hote$2.ref([]);
    const gravite = __hote$2.ref("");
    const charge = __hote$2.ref(false);
    const message = __hote$2.ref("");
    const aRetirer = __hote$2.ref(null);
    function taille(octets) {
      const go = octets / 1e9;
      return go >= 1 ? `${go.toFixed(1)} Go` : `${Math.round(octets / 1e6)} Mo`;
    }
    async function charger(depuisLeDebut = true) {
      const params = { pending_review: 0, limit: 100, offset: depuisLeDebut ? 0 : items.value.length };
      if (gravite.value) params.severity = gravite.value;
      const page = await api2.get(BASE, params);
      items.value = depuisLeDebut ? page.items : items.value.concat(page.items);
      total.value = page.total;
      enAttente.value = (await api2.get(BASE, { pending_review: 1, limit: 200 })).items;
      charge.value = true;
    }
    async function geste(fn, fait) {
      var _a, _b;
      message.value = "";
      try {
        const r = await fn();
        message.value = typeof fait === "function" ? fait(r) : fait;
        await charger();
      } catch (e) {
        message.value = ((_b = (_a = e == null ? void 0 : e.response) == null ? void 0 : _a.data) == null ? void 0 : _b.detail) || (e == null ? void 0 : e.message) || "Le geste a échoué.";
      }
    }
    function retirer(i) {
      if (aRetirer.value !== i.artist_id) {
        aRetirer.value = i.artist_id;
        return;
      }
      aRetirer.value = null;
      oublier(i.artist_id);
      geste(() => api2.delete(`${BASE}/${i.artist_id}`), "Signalement retiré.");
    }
    function corbeille(i) {
      geste(
        () => api2.post("/operations/staged", [{ operation_type: "trash_artist", source: "safeplace", target_type: "artist", target_id: i.artist_id }]),
        (rendues) => [].concat(rendues || []).every((o) => o.status === "pending") ? `« ${i.artist_name} » attend au tampon (Opérations).` : `« ${i.artist_name} » : opération envoyée.`
      );
    }
    __hote$2.watch(gravite, () => charger());
    __hote$2.onMounted(() => charger());
    return (_ctx, _cache) => {
      return __hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_1$1, [
        _cache[8] || (_cache[8] = __hote$2.createElementVNode("header", null, [
          __hote$2.createElementVNode("h2", { style: { "font-size": "1.5rem", "font-weight": "700" } }, "Safeplace"),
          __hote$2.createElementVNode("p", { style: { "font-size": "0.875rem", "color": "var(--color-ink-muted)" } }, " Les artistes que vous avez signalés, et ceux que l'assistant suggère. Un signalement ne touche à aucun fichier : la corbeille passe par le tampon d'opérations. ")
        ], -1)),
        enAttente.value.length ? (__hote$2.openBlock(), __hote$2.createElementBlock("section", _hoisted_2$1, [
          __hote$2.createElementVNode("h3", _hoisted_3$1, "En attente de validation · " + __hote$2.toDisplayString(enAttente.value.length), 1),
          (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(enAttente.value, (i) => {
            return __hote$2.openBlock(), __hote$2.createElementBlock("div", {
              key: i.artist_id,
              style: { "display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "var(--space-2)" }
            }, [
              __hote$2.createVNode(__hote$2.unref(__hote$1.RouterLink), {
                to: `/library/artists/${i.artist_id}`,
                style: { "font-weight": "600" }
              }, {
                default: __hote$2.withCtx(() => [
                  __hote$2.createTextVNode(__hote$2.toDisplayString(i.artist_name), 1)
                ]),
                _: 2
              }, 1032, ["to"]),
              __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                tone: TON[i.severity]
              }, {
                default: __hote$2.withCtx(() => [
                  __hote$2.createTextVNode(__hote$2.toDisplayString(__hote$2.unref(GRAVITES)[i.severity]), 1)
                ]),
                _: 2
              }, 1032, ["tone"]),
              __hote$2.createElementVNode("span", _hoisted_4$1, __hote$2.toDisplayString(i.reasons), 1),
              __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                intent: "primary",
                size: "sm",
                onClick: ($event) => geste(() => __hote$2.unref(api2).put(`${BASE}/${i.artist_id}/confirm`), "Signalement confirmé.")
              }, {
                default: __hote$2.withCtx(() => [..._cache[2] || (_cache[2] = [
                  __hote$2.createTextVNode("Confirmer", -1)
                ])]),
                _: 1
              }, 8, ["onClick"]),
              __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                intent: "ghost",
                size: "sm",
                onClick: ($event) => geste(() => __hote$2.unref(api2).delete(`${BASE}/${i.artist_id}`), "Suggestion rejetée.")
              }, {
                default: __hote$2.withCtx(() => [..._cache[3] || (_cache[3] = [
                  __hote$2.createTextVNode("Rejeter", -1)
                ])]),
                _: 1
              }, 8, ["onClick"])
            ]);
          }), 128))
        ])) : __hote$2.createCommentVNode("", true),
        __hote$2.createElementVNode("div", _hoisted_5$1, [
          __hote$2.createVNode(__hote$2.unref(__hote.UiSelect), {
            modelValue: gravite.value,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => gravite.value = $event),
            label: "Gravité"
          }, {
            default: __hote$2.withCtx(() => [
              _cache[4] || (_cache[4] = __hote$2.createElementVNode("option", { value: "" }, "Toutes", -1)),
              (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(__hote$2.unref(GRAVITES), (libelle, cle) => {
                return __hote$2.openBlock(), __hote$2.createElementBlock("option", {
                  key: cle,
                  value: cle
                }, __hote$2.toDisplayString(libelle), 9, _hoisted_6$1);
              }), 128))
            ]),
            _: 1
          }, 8, ["modelValue"])
        ]),
        message.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("p", _hoisted_7, __hote$2.toDisplayString(message.value), 1)) : __hote$2.createCommentVNode("", true),
        charge.value && !items.value.length ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiEmpty), {
          key: 2,
          title: "Aucun artiste signalé",
          description: "Signalez un artiste depuis sa fiche, par « Actions »."
        })) : __hote$2.createCommentVNode("", true),
        __hote$2.createElementVNode("ul", _hoisted_8, [
          (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(items.value, (i) => {
            return __hote$2.openBlock(), __hote$2.createElementBlock("li", {
              key: i.artist_id,
              "data-test": "safeplace-ligne",
              style: { "display": "flex", "flex-wrap": "wrap", "align-items": "center", "gap": "var(--space-2)", "padding": "var(--space-3)", "border": "1px solid var(--color-border)", "border-radius": "var(--radius-lg)", "background": "var(--color-surface)" }
            }, [
              __hote$2.createElementVNode("div", _hoisted_9, [
                __hote$2.createElementVNode("div", _hoisted_10, [
                  __hote$2.createVNode(__hote$2.unref(__hote$1.RouterLink), {
                    to: `/library/artists/${i.artist_id}`,
                    style: { "font-weight": "600" }
                  }, {
                    default: __hote$2.withCtx(() => [
                      __hote$2.createTextVNode(__hote$2.toDisplayString(i.artist_name), 1)
                    ]),
                    _: 2
                  }, 1032, ["to"]),
                  __hote$2.createVNode(__hote$2.unref(__hote.UiChip), {
                    tone: TON[i.severity]
                  }, {
                    default: __hote$2.withCtx(() => [
                      __hote$2.createTextVNode(__hote$2.toDisplayString(__hote$2.unref(GRAVITES)[i.severity]), 1)
                    ]),
                    _: 2
                  }, 1032, ["tone"])
                ]),
                __hote$2.createElementVNode("span", _hoisted_11, __hote$2.toDisplayString(i.genre_name || "—") + " · " + __hote$2.toDisplayString(i.album_count) + " album(s) · " + __hote$2.toDisplayString(taille(i.total_size_bytes)), 1),
                i.reasons ? (__hote$2.openBlock(), __hote$2.createElementBlock("span", _hoisted_12, __hote$2.toDisplayString(i.reasons), 1)) : __hote$2.createCommentVNode("", true),
                __hote$2.createElementVNode("span", _hoisted_13, [
                  __hote$2.createTextVNode(__hote$2.toDisplayString(__hote$2.unref(PAR)[i.flagged_by] || i.flagged_by) + " · " + __hote$2.toDisplayString(__hote$2.unref(dateCourte)(i.flagged_at)) + " ", 1),
                  i.source_url ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
                    _cache[5] || (_cache[5] = __hote$2.createTextVNode(" · ", -1)),
                    __hote$2.createElementVNode("a", {
                      href: i.source_url,
                      target: "_blank",
                      rel: "noopener",
                      style: { "text-decoration": "underline" }
                    }, "source", 8, _hoisted_14)
                  ], 64)) : __hote$2.createCommentVNode("", true)
                ])
              ]),
              __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                intent: "danger",
                size: "sm",
                onClick: ($event) => corbeille(i)
              }, {
                default: __hote$2.withCtx(() => [..._cache[6] || (_cache[6] = [
                  __hote$2.createTextVNode("Proposer la corbeille", -1)
                ])]),
                _: 1
              }, 8, ["onClick"]),
              __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
                intent: "ghost",
                size: "sm",
                onClick: ($event) => retirer(i)
              }, {
                default: __hote$2.withCtx(() => [
                  __hote$2.createTextVNode(__hote$2.toDisplayString(aRetirer.value === i.artist_id ? "Confirmer le retrait" : "Retirer"), 1)
                ]),
                _: 2
              }, 1032, ["onClick"])
            ]);
          }), 128))
        ]),
        items.value.length < total.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_15, [
          __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
            intent: "secondary",
            size: "sm",
            onClick: _cache[1] || (_cache[1] = ($event) => charger(false))
          }, {
            default: __hote$2.withCtx(() => [..._cache[7] || (_cache[7] = [
              __hote$2.createTextVNode("Afficher plus", -1)
            ])]),
            _: 1
          })
        ])) : __hote$2.createCommentVNode("", true)
      ]);
    };
  }
};
const _hoisted_1 = {
  "data-test": "safeplace-signaler",
  style: { "display": "grid", "gap": "var(--space-3)" }
};
const _hoisted_2 = { style: { "font-size": "0.875rem" } };
const _hoisted_3 = {
  key: 0,
  style: { "font-size": "0.875rem", "color": "var(--color-ink-muted)" }
};
const _hoisted_4 = { style: { "display": "flex", "flex-wrap": "wrap", "gap": "var(--space-2)" } };
const _hoisted_5 = ["value"];
const _hoisted_6 = {
  key: 2,
  role: "status",
  style: { "font-size": "0.75rem", "color": "var(--color-ink-muted)" }
};
const _sfc_main = {
  __name: "Signaler",
  props: { artiste: { type: Object, required: true } },
  setup(__props) {
    const props = __props;
    const { api: api2 } = globalThis.__unisson__;
    const item = __hote$2.ref(null);
    const form = __hote$2.reactive({ reasons: "", severity: "autre", source_url: "" });
    const occupe = __hote$2.ref(false);
    const aConfirmer = __hote$2.ref(false);
    const message = __hote$2.ref("");
    async function relire() {
      oublier(props.artiste.id);
      item.value = await signalement(props.artiste.id);
    }
    async function geste(fn, fait) {
      var _a, _b;
      occupe.value = true;
      message.value = "";
      try {
        await fn();
        message.value = fait;
        await relire();
      } catch (e) {
        message.value = ((_b = (_a = e == null ? void 0 : e.response) == null ? void 0 : _a.data) == null ? void 0 : _b.detail) || (e == null ? void 0 : e.message) || "Le geste a échoué.";
      } finally {
        occupe.value = false;
      }
    }
    const poser = () => geste(() => api2.post("/plugins/safeplace/flags", {
      artist_id: props.artiste.id,
      reasons: form.reasons.trim(),
      severity: form.severity,
      source_url: form.source_url.trim() || null
    }), "Artiste signalé.");
    const confirmer = () => geste(() => api2.put(`/plugins/safeplace/flags/${props.artiste.id}/confirm`), "Signalement confirmé.");
    function retirer() {
      if (!aConfirmer.value) {
        aConfirmer.value = true;
        return;
      }
      aConfirmer.value = false;
      geste(() => api2.delete(`/plugins/safeplace/flags/${props.artiste.id}`), "Signalement retiré.");
    }
    __hote$2.onMounted(async () => {
      item.value = await signalement(props.artiste.id);
    });
    return (_ctx, _cache) => {
      return __hote$2.openBlock(), __hote$2.createElementBlock("div", _hoisted_1, [
        item.value ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
          __hote$2.createElementVNode("p", _hoisted_2, [
            __hote$2.createTextVNode(" Déjà signalé — " + __hote$2.toDisplayString(__hote$2.unref(GRAVITES)[item.value.severity] || item.value.severity), 1),
            item.value.pending_review ? (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 0 }, [
              __hote$2.createTextVNode(", en attente de validation")
            ], 64)) : __hote$2.createCommentVNode("", true),
            _cache[3] || (_cache[3] = __hote$2.createTextVNode(". ", -1))
          ]),
          item.value.reasons ? (__hote$2.openBlock(), __hote$2.createElementBlock("p", _hoisted_3, __hote$2.toDisplayString(item.value.reasons), 1)) : __hote$2.createCommentVNode("", true),
          __hote$2.createElementVNode("div", _hoisted_4, [
            item.value.pending_review ? (__hote$2.openBlock(), __hote$2.createBlock(__hote$2.unref(__hote.UiButton), {
              key: 0,
              intent: "primary",
              size: "sm",
              loading: occupe.value,
              onClick: confirmer
            }, {
              default: __hote$2.withCtx(() => [..._cache[4] || (_cache[4] = [
                __hote$2.createTextVNode("Confirmer", -1)
              ])]),
              _: 1
            }, 8, ["loading"])) : __hote$2.createCommentVNode("", true),
            __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
              intent: aConfirmer.value ? "danger" : "secondary",
              size: "sm",
              loading: occupe.value,
              onClick: retirer
            }, {
              default: __hote$2.withCtx(() => [
                __hote$2.createTextVNode(__hote$2.toDisplayString(aConfirmer.value ? "Confirmer le retrait" : "Retirer le signalement"), 1)
              ]),
              _: 1
            }, 8, ["intent", "loading"])
          ])
        ], 64)) : (__hote$2.openBlock(), __hote$2.createElementBlock(__hote$2.Fragment, { key: 1 }, [
          __hote$2.createVNode(__hote$2.unref(__hote.UiField), {
            modelValue: form.reasons,
            "onUpdate:modelValue": _cache[0] || (_cache[0] = ($event) => form.reasons = $event),
            label: "Motif",
            placeholder: "Accusations, condamnations, sources…",
            block: ""
          }, null, 8, ["modelValue"]),
          __hote$2.createVNode(__hote$2.unref(__hote.UiSelect), {
            modelValue: form.severity,
            "onUpdate:modelValue": _cache[1] || (_cache[1] = ($event) => form.severity = $event),
            label: "Gravité"
          }, {
            default: __hote$2.withCtx(() => [
              (__hote$2.openBlock(true), __hote$2.createElementBlock(__hote$2.Fragment, null, __hote$2.renderList(__hote$2.unref(GRAVITES), (libelle, cle) => {
                return __hote$2.openBlock(), __hote$2.createElementBlock("option", {
                  key: cle,
                  value: cle
                }, __hote$2.toDisplayString(libelle), 9, _hoisted_5);
              }), 128))
            ]),
            _: 1
          }, 8, ["modelValue"]),
          __hote$2.createVNode(__hote$2.unref(__hote.UiField), {
            modelValue: form.source_url,
            "onUpdate:modelValue": _cache[2] || (_cache[2] = ($event) => form.source_url = $event),
            label: "Lien vers la source",
            placeholder: "https://…",
            block: ""
          }, null, 8, ["modelValue"]),
          __hote$2.createElementVNode("div", null, [
            __hote$2.createVNode(__hote$2.unref(__hote.UiButton), {
              intent: "primary",
              size: "sm",
              loading: occupe.value,
              "data-test": "safeplace-envoyer",
              onClick: poser
            }, {
              default: __hote$2.withCtx(() => [..._cache[5] || (_cache[5] = [
                __hote$2.createTextVNode("Signaler", -1)
              ])]),
              _: 1
            }, 8, ["loading"])
          ])
        ], 64)),
        message.value ? (__hote$2.openBlock(), __hote$2.createElementBlock("p", _hoisted_6, __hote$2.toDisplayString(message.value), 1)) : __hote$2.createCommentVNode("", true)
      ]);
    };
  }
};
function installer(hote2, enregistrer) {
  enregistrer.page({ chemin: "/", libelle: "Safeplace", icone: "⚑", composant: _sfc_main$1 });
  enregistrer.emplacement("fiche-artiste.entete", { composant: _sfc_main$3 });
  enregistrer.emplacement("fiche-artiste.blocs", { titre: "Signalement", composant: _sfc_main$2 });
  enregistrer.emplacement("fiche-artiste.hub", {
    titre: "Signaler",
    description: "Signaler cet artiste, ou revoir son signalement.",
    ecran: _sfc_main
  });
}
export {
  installer
};
