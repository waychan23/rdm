<template>
  <span class="rdm-chip" :class="tone">{{ status }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{ status: string }>();

const DONE = ["DONE", "PUBLISHED", "CLOSED", "CANCELLED", "REJECTED", "COMPLETED"];
const TODO = ["TODO", "OPEN", "PLANNED", "BACKLOG", "NEW", "DRAFT"];

const tone = computed(() => {
  const s = props.status.toUpperCase();
  if (s.includes("BLOCK")) return "blocked";
  if (DONE.some((d) => s === d || s.endsWith("_" + d))) return "done";
  if (TODO.includes(s)) return "todo";
  return "doing";
});
</script>

<style scoped>
.rdm-chip {
  display: inline-flex;
  align-items: center;
  height: var(--rdm-chip-h);
  padding: 0 var(--rdm-space-4);
  border-radius: var(--rdm-chip-radius);
  font: var(--rdm-chip-font);
  white-space: nowrap;
}
.doing {
  background: var(--rdm-chip-doing-bg);
  color: var(--rdm-chip-doing-fg);
}
.todo {
  background: var(--rdm-chip-todo-bg);
  color: var(--rdm-chip-todo-fg);
}
.done {
  background: var(--rdm-chip-done-bg);
  color: var(--rdm-chip-done-fg);
}
.blocked {
  background: var(--rdm-chip-blocked-bg);
  color: var(--rdm-chip-blocked-fg);
}
</style>
