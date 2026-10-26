<template>
  <div class="board-page" v-loading="loading">
    <header class="board-head">
      <div class="page-title">看板</div>
      <el-radio-group v-model="kind" size="small" @change="load">
        <el-radio-button v-for="k in KINDS" :key="k.value" :value="k.value">
          {{ k.label }}
        </el-radio-button>
      </el-radio-group>
      <el-checkbox v-model="showTerminal" size="small" @change="load">显示终态列</el-checkbox>
    </header>

    <div class="board">
      <div
        v-for="col in columns"
        :key="col.status"
        class="column"
        @dragover.prevent="dragOver = col.status"
        @dragleave="dragOver = null"
        @drop.prevent="onDrop(col.status)"
        :class="{ 'drop-target': dragOver === col.status }"
      >
        <div class="column-head">
          <StatusPill :status="col.status" />
          <span class="count rdm-num">{{ col.items.length }}</span>
        </div>
        <div class="card-list">
          <div
            v-for="item in col.items"
            :key="item.id"
            class="card"
            draggable="true"
            @dragstart="onDragStart(item, $event)"
            @dragend="dragOver = null"
            @click="openItem(item)"
          >
            <div class="card-top">
              <TypeIcon :kind="item.kind" />
              <span class="rdm-num card-id">{{ item.display_id }}</span>
              <PriorityRank :priority="item.priority" />
            </div>
            <div class="card-title">{{ item.title }}</div>
            <div class="card-foot">
              <PersonCell :name="item.assignee?.name" />
            </div>
          </div>
          <el-empty
            v-if="!col.items.length"
            :image-size="48"
            description=""
            class="empty-col"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api, errorCause } from "../api";
import type { WorkItem, WorkflowDto } from "../types";
import StatusPill from "../components/StatusPill.vue";
import PriorityRank from "../components/PriorityRank.vue";
import PersonCell from "../components/PersonCell.vue";
import TypeIcon from "../components/TypeIcon.vue";

const KINDS = [
  { value: "epic", label: "Epic" },
  { value: "story", label: "需求" },
  { value: "issue", label: "缺陷" },
  { value: "task", label: "任务" },
];

defineProps<{ key?: string }>();
const route = useRoute();
const router = useRouter();
const key = String(route.params.key);
const kind = ref("task");
const showTerminal = ref(true);
const loading = ref(false);
const items = ref<WorkItem[]>([]);
const workflow = ref<WorkflowDto | null>(null);
const dragged = ref<WorkItem | null>(null);
const dragOver = ref<string | null>(null);

const columns = computed(() => {
  const spec = workflow.value?.kinds[kind.value];
  if (!spec) return [];
  const terminal = new Set(spec.terminal);
  const states = spec.states.filter((s) => showTerminal.value || !terminal.has(s));
  return states.map((status) => ({
    status,
    items: items.value.filter((i) => i.status === status),
  }));
});

async function load() {
  loading.value = true;
  try {
    const params = new URLSearchParams({ kind: kind.value, limit: "200" });
    const [wf, list] = await Promise.all([
      workflow.value
        ? Promise.resolve({ data: workflow.value })
        : api.get<WorkflowDto>("/workflow"),
      api.get<WorkItem[]>(`/projects/${key}/work-items?${params}`),
    ]);
    workflow.value = wf.data;
    items.value = list.data;
  } finally {
    loading.value = false;
  }
}

function onDragStart(item: WorkItem, event: DragEvent) {
  dragged.value = item;
  event.dataTransfer?.setData("text/plain", item.id);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
}

async function onDrop(target: string) {
  dragOver.value = null;
  const item = dragged.value;
  dragged.value = null;
  if (!item || item.status === target) return;
  // Only legal transitions are attempted; the server enforces the graph/gate.
  const allowed = workflow.value?.kinds[item.kind]?.transitions[item.status] ?? [];
  if (!allowed.includes(target)) {
    ElMessage.warning(`${item.display_id} 不能从 ${item.status} 流转到 ${target}`);
    return;
  }
  const previous = item.status;
  // optimistic
  item.status = target;
  try {
    await api.post(`/work-items/${item.display_id}/transition`, {
      to: target,
      row_version: item.row_version,
      reason: null,
    });
    ElMessage.success(`${item.display_id} → ${target}`);
    await load();
  } catch (e) {
    item.status = previous;
    const cause = errorCause(e);
    if (cause?.details?.blocking_children) {
      const ids = (cause.details.blocking_children as { display_id?: string }[])
        .map((c) => c.display_id)
        .join(", ");
      ElMessage.error(`${cause.message}（阻塞: ${ids}）`);
    } else {
      ElMessage.error(cause?.message || "流转失败");
    }
  }
}

function openItem(item: WorkItem) {
  router.push(`/projects/${key}/items/${item.id}`);
}

onMounted(load);
</script>

<style scoped>
.board-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--rdm-page-pad-y) var(--rdm-page-pad-x);
  box-sizing: border-box;
}
.board-head {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-4);
  margin-bottom: var(--rdm-space-4);
}
.page-title {
  font: var(--rdm-type-page-title);
}
.board {
  flex: 1;
  display: flex;
  gap: var(--rdm-space-2);
  overflow-x: auto;
  align-items: stretch;
}
.column {
  flex: 0 0 280px;
  background: var(--rdm-surface-subtle);
  border-radius: var(--rdm-radius-2);
  padding: var(--rdm-space-2);
  display: flex;
  flex-direction: column;
}
.column.drop-target {
  outline: 2px dashed var(--rdm-accent);
  outline-offset: -2px;
}
.column-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 32px;
  padding: 0 var(--rdm-space-2) var(--rdm-space-2);
}
.count {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-3);
}
.card-list {
  display: flex;
  flex-direction: column;
  gap: var(--rdm-space-2);
  min-height: 80px;
}
.card {
  background: var(--rdm-surface);
  border: 1px solid var(--rdm-border);
  border-radius: var(--rdm-radius-2);
  padding: var(--rdm-space-3);
  cursor: grab;
}
.card:active {
  cursor: grabbing;
}
.card:hover {
  border-color: var(--rdm-border-strong);
}
.card-top {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-2);
}
.card-id {
  color: var(--rdm-accent-strong);
  font: var(--rdm-type-meta);
}
.card-title {
  margin: var(--rdm-space-2) 0;
  font: var(--rdm-type-body);
  color: var(--rdm-text-1);
}
.card-foot {
  color: var(--rdm-text-3);
}
.empty-col {
  opacity: 0.5;
}
</style>
