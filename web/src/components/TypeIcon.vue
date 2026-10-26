<template>
  <span class="type-icon" :class="kind">{{ label }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ kind: string }>();
const LABELS: Record<string, string> = {
  epic: "E",
  story: "需",
  issue: "缺",
  task: "任",
};
const label = computed(() => LABELS[props.kind] ?? props.kind);
</script>

<style scoped>
.type-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: var(--rdm-radius-1);
  font: var(--rdm-type-meta);
  color: var(--rdm-text-on-accent);
}
.story {
  background: var(--rdm-type-requirement);
}
.task {
  background: var(--rdm-type-task);
}
.issue {
  background: var(--rdm-type-bug);
}
.epic {
  background: var(--rdm-text-3);
}
</style>
