<template>
  <div :role="role" :style="{
    display: 'flex', gap: 'var(--space-2-5)', alignItems: 'flex-start', padding: 'var(--space-2-5) var(--space-3-5)',
    borderRadius: 'var(--radius-md)', fontSize: 'var(--text-sm)', background: `var(--color-${TONS[ton].fond})`,
  }">
    <span :style="{ color: `var(--color-${TONS[ton].icone})`, marginTop: '2px', display: 'inline-flex' }">
      <Icone :nom="ton === 'info' ? 'info' : 'alert'" />
    </span>
    <div style="display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; flex: 1">
      <slot />
    </div>
    <slot name="actions" />
  </div>
</template>

<script setup>
// Le bandeau d'alerte du prototype (même dessin que les notes des écrans
// validés) : un fond doux, une icône dans la couleur du ton.
import Icone from "./Icone.vue";

defineProps({ ton: { type: String, default: "info" }, role: { type: String, default: "status" } });

const TONS = {
  info: { fond: "accent-soft", icone: "accent" },
  warning: { fond: "warning-soft", icone: "warning" },
  danger: { fond: "danger-soft", icone: "danger" },
};
</script>
