<template>
  <div class="page">
    <header class="page-header">
      <div class="page-title">{{ projectKey }} 概览</div>
      <div class="quick">
        <el-button size="small" @click="go('board')">看板</el-button>
        <el-button size="small" @click="go('backlog')">工作项</el-button>
        <el-button size="small" @click="go('sprints')">迭代</el-button>
        <el-button size="small" @click="go('mailbox')">信箱</el-button>
      </div>
    </header>

    <div v-if="data" class="grid">
      <section class="stat-cards">
        <div class="stat">
          <div class="stat-num rdm-num">{{ data.total_items }}</div>
          <div class="stat-label">全部工作项</div>
        </div>
        <div class="stat">
          <div class="stat-num rdm-num">{{ data.open_items }}</div>
          <div class="stat-label">未完成</div>
        </div>
        <div class="stat">
          <div class="stat-num rdm-num">{{ data.my_open_items }}</div>
          <div class="stat-label">我的待办</div>
        </div>
        <div class="stat">
          <div class="stat-num rdm-num">{{ data.members }}</div>
          <div class="stat-label">成员</div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">类型分布</div>
        <div class="kind-row" v-for="(count, kind) in data.by_kind" :key="kind">
          <TypeIcon :kind="kind" />
          <span class="kind-name">{{ kindLabel(kind) }}</span>
          <span class="kind-count rdm-num">{{ count }}</span>
        </div>
      </section>

      <section class="panel">
        <div class="panel-title">状态分布</div>
        <div class="status-row" v-for="(count, status) in data.by_status" :key="status">
          <StatusPill :status="status" />
          <span class="status-count rdm-num">{{ count }}</span>
        </div>
      </section>

      <section v-if="data.active_sprint" class="panel">
        <div class="panel-title">进行中迭代 · {{ data.active_sprint.name }}</div>
        <div class="sprint-total rdm-num">
          共 {{ data.active_sprint.total }} 项
        </div>
        <div class="status-row" v-for="(c, s) in data.active_sprint.by_status" :key="s">
          <StatusPill :status="s" />
          <span class="status-count rdm-num">{{ c }}</span>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import StatusPill from "../components/StatusPill.vue";
import TypeIcon from "../components/TypeIcon.vue";

interface Overview {
  total_items: number;
  open_items: number;
  my_open_items: number;
  members: number;
  by_kind: Record<string, number>;
  by_status: Record<string, number>;
  active_sprint: {
    name: string;
    total: number;
    by_status: Record<string, number>;
  } | null;
}

const route = useRoute();
const router = useRouter();
const projectKey = () => String(route.params.key);
const data = ref<Overview | null>(null);

const KIND_LABELS: Record<string, string> = {
  epic: "Epic",
  story: "需求",
  issue: "缺陷",
  task: "任务",
};
function kindLabel(k: string) {
  return KIND_LABELS[k] ?? k;
}
function go(page: string) {
  router.push(`/projects/${projectKey()}/${page}`);
}
async function load() {
  data.value = (await api.get<Overview>(`/projects/${projectKey()}/overview`)).data;
}
onMounted(load);
watch(() => route.params.key, load);
</script>

<style scoped>
.page {
  padding: var(--rdm-page-pad-y) var(--rdm-page-pad-x);
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--rdm-space-6);
}
.page-title {
  font: var(--rdm-type-page-title);
}
.quick {
  display: flex;
  gap: var(--rdm-space-2);
}
.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 360px));
  gap: var(--rdm-gutter);
  align-items: start;
}
.stat-cards {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--rdm-gutter);
}
.stat {
  border: 1px solid var(--rdm-border);
  border-radius: var(--rdm-radius-2);
  padding: var(--rdm-space-5);
}
.stat-num {
  font: var(--rdm-type-num);
  color: var(--rdm-text-1);
}
.stat-label {
  margin-top: var(--rdm-space-1);
  font: var(--rdm-type-meta);
  color: var(--rdm-text-3);
}
.panel {
  border: 1px solid var(--rdm-border);
  border-radius: var(--rdm-radius-2);
  padding: var(--rdm-space-5);
}
.panel-title {
  font: var(--rdm-type-section);
  margin-bottom: var(--rdm-space-4);
  color: var(--rdm-text-1);
}
.kind-row,
.status-row {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-3);
  padding: var(--rdm-space-2) 0;
  font: var(--rdm-type-body);
}
.kind-name {
  flex: 1;
}
.kind-count,
.status-count {
  color: var(--rdm-text-2);
}
.sprint-total {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-3);
  margin-bottom: var(--rdm-space-3);
}
</style>
