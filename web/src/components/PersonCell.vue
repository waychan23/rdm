<template>
  <span class="person">
    <span class="avatar">{{ initial }}</span>
    <span class="name">{{ name || "未指派" }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ name?: string | null }>();
const initial = computed(() => (props.name ? props.name.slice(0, 1).toUpperCase() : "?"));
</script>

<style scoped>
.person {
  display: inline-flex;
  align-items: center;
  gap: var(--rdm-space-2);
  font: var(--rdm-type-cell);
  color: var(--rdm-text-2);
}
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--rdm-radius-pill);
  background: var(--rdm-avatar-bg);
  color: var(--rdm-text-on-accent);
  font: var(--rdm-type-meta);
}
.name:only-child,
.person > .name {
  color: var(--rdm-text-2);
}
</style>
