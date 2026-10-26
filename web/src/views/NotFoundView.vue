<template>
  <div class="nf">
    <div class="code rdm-num">404</div>
    <div class="hint">页面不存在</div>
    <el-button type="primary" @click="router.push('/projects')">回到项目</el-button>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from "vue-router";
const router = useRouter();
</script>

<style scoped>
.nf {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--rdm-space-4);
  background: var(--rdm-surface);
}
.code {
  font-size: var(--rdm-font-size-24);
  color: var(--rdm-text-1);
}
.hint {
  font: var(--rdm-type-body);
  color: var(--rdm-text-3);
}
</style>
