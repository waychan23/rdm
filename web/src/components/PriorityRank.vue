<template>
  <span class="priority" :class="{ unset: priority == null }">
    <span class="dot" />
    <span>{{ priority == null ? "未设置" : priority }}</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{ priority: number | null }>();
</script>

<style scoped>
.priority {
  display: inline-flex;
  align-items: center;
  gap: var(--rdm-space-2);
  font: var(--rdm-type-cell);
  color: var(--rdm-text-1);
}
.priority.unset {
  color: var(--rdm-text-3);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--rdm-warning);
}
.priority.unset .dot {
  background: var(--rdm-text-disabled);
}
</style>
