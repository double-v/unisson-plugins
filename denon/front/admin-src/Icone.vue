<template>
  <svg :style="{ width: taille, height: taille, flex: '0 0 auto' }" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="TRACES[nom] || ''" />
</template>

<script setup>
// Les icônes du prototype validé, au trait (24 × 24).
defineProps({ nom: { type: String, required: true }, taille: { type: String, default: "1.15em" } });

const TRACES = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  play: '<path d="M7 5v14l11-7z"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
  alert: '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  check: '<path d="M5 12.5 10 17l9-10"/>',
  back: '<path d="M15 6l-6 6 6 6"/>',
  spin: '<path d="M12 3a9 9 0 1 0 9 9"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  link: '<path d="M10 14 21 3M15 3h6v6M19 14v6H4V5h6"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
};
</script>
