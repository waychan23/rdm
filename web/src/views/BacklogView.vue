<template>
  <div class="page">
    <header class="page-header">
      <div>
        <div class="page-title">工作项</div>
      </div>
      <div class="toolbar">
        <el-checkbox-group v-model="kinds" size="small" @change="reload(1)">
          <el-checkbox-button v-for="k in KIND_OPTIONS" :key="k.value" :value="k.value">
            {{ k.label }}
          </el-checkbox-button>
        </el-checkbox-group>
        <el-select v-model="status" size="small" clearable placeholder="状态" style="width: 140px" @change="reload(1)">
          <el-option v-for="s in statusOptions" :key="s" :value="s" :label="s" />
        </el-select>
        <el-select v-model="assignee" size="small" clearable placeholder="负责人" style="width: 140px" @change="reload(1)">
          <el-option value="me" label="我的" />
          <el-option v-for="m in members" :key="m.id" :value="m.id" :label="m.name" />
        </el-select>
        <el-input v-model="q" size="small" clearable placeholder="搜索标题" style="width: 180px" @change="reload(1)" />
        <el-button size="small" type="primary" @click="showCreate = true">新建</el-button>
      </div>
    </header>

    <WorkItemTable
      :items="items"
      :total="total"
      :page="page"
      :page-size="pageSize"
      @open="openItem"
      @update:page="reload"
    />

    <CreateWorkItem
      v-model="showCreate"
      :project-key="projectKey"
      @created="onCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "../api";
import type { Member, WorkItem, WorkflowDto } from "../types";
import WorkItemTable from "../components/WorkItemTable.vue";
import CreateWorkItem from "../components/CreateWorkItem.vue";

const route = useRoute();
const router = useRouter();
const projectKey = (route.params.key as string) || "RDM";

const items = ref<WorkItem[]>([]);
const members = ref<Member[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const kinds = ref<string[]>(["epic", "story", "issue", "task"]);
const status = ref("");
const assignee = ref("");
const q = ref("");
const showCreate = ref(false);
const statusOptions = ref<string[]>([]);

const KIND_OPTIONS = [
  { value: "epic", label: "Epic" },
  { value: "story", label: "需求" },
  { value: "issue", label: "缺陷" },
  { value: "task", label: "任务" },
];

async function reload(p = page.value) {
  page.value = p;
  const params: Record<string, string | number> = {
    limit: pageSize,
    offset: (p - 1) * pageSize,
  };
  if (kinds.value.length === 1) params.kind = kinds.value[0];
  if (status.value) params.status = status.value;
  if (assignee.value) params.assignee = assignee.value === "me" ? "me" : assignee.value;
  if (q.value) params.q = q.value;
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => query.set(k, String(v)));
  const res = await api.get<WorkItem[]>(
    `/projects/${projectKey}/work-items?${query.toString()}`
  );
  items.value = res.data;
  total.value = Number(res.meta?.total ?? res.data.length);
}

function openItem(item: WorkItem) {
  router.push(`/projects/${projectKey}/items/${item.id}`);
}
function onCreated(item: WorkItem) {
  reload(1);
  openItem(item);
}

onMounted(async () => {
  members.value = (await api.get<Member[]>(`/projects/${projectKey}/members`)).data;
  const wf = (await api.get<WorkflowDto>("/workflow")).data;
  statusOptions.value = [...new Set(Object.values(wf.kinds).flatMap((k) => k.states))];
  reload(1);
});
watch(() => route.params.key, () => reload(1));
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: var(--rdm-page-pad-y) var(--rdm-page-pad-x);
  box-sizing: border-box;
}
.page-header {
  margin-bottom: var(--rdm-space-4);
}
.page-title {
  font: var(--rdm-type-page-title);
  color: var(--rdm-text-1);
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-2);
  margin-top: var(--rdm-space-3);
  flex-wrap: wrap;
}
</style>
