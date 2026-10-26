<template>
  <div v-loading="loading">
    <div class="head">
      <h2>看板 · {{ key }}</h2>
      <el-radio-group v-model="kind" size="small" @change="load">
        <el-radio-button v-for="k in KINDS" :key="k" :value="k">{{ k }}</el-radio-button>
      </el-radio-group>
    </div>
    <div class="board">
      <div v-for="col in columns" :key="col.status" class="column">
        <div class="column-head">
          <span>{{ col.status }}</span>
          <el-tag size="small" round>{{ col.items.length }}</el-tag>
        </div>
        <router-link
          v-for="item in col.items"
          :key="item.id"
          :to="`/projects/${key}/items/${item.display_id}`"
          class="card"
        >
          <div class="card-id">{{ item.display_id }}</div>
          <div class="card-title">{{ item.title }}</div>
          <div class="card-assignee">{{ item.assignee?.name ?? "未指派" }}</div>
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { WorkItem, WorkflowDto } from "../types";

const KINDS = ["story", "task", "issue"];
const props = defineProps<{ key: string }>();
const key = props.key;
const kind = ref("task");
const loading = ref(false);
const items = ref<WorkItem[]>([]);
const workflow = ref<WorkflowDto | null>(null);

const columns = computed(() => {
  const spec = workflow.value?.kinds[kind.value];
  const states = spec?.states ?? [];
  const terminal = new Set(spec?.terminal ?? []);
  const shown = states.filter((s) => !terminal.has(s));
  return shown.map((status) => ({
    status,
    items: items.value.filter((i) => i.status === status),
  }));
});

async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams({ kind: kind.value, limit: "200" });
    const [wf, list] = await Promise.all([
      api.get<WorkflowDto>("/workflow"),
      api.get<WorkItem[]>(`/projects/${key}/work-items?${params}`),
    ]);
    workflow.value = wf.data;
    items.value = list.data;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.board {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 12px;
}
.column {
  flex: 1 0 220px;
  background: var(--el-fill-color-light);
  border-radius: var(--rdm-radius-2);
  padding: 8px;
}
.column-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
  padding: 4px 6px 8px;
}
.card {
  display: block;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: var(--rdm-radius-2);
  padding: 8px 10px;
  margin-bottom: 8px;
  text-decoration: none;
  color: inherit;
}
.card:hover {
  border-color: var(--el-color-primary);
}
.card-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.card-title {
  font-size: 12px;
  margin: 2px 0 4px;
}
.card-assignee {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
