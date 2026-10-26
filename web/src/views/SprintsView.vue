<template>
  <div v-loading="loading">
    <div class="head">
      <h2>Sprint · {{ key }}</h2>
      <el-button type="primary" @click="openCreate">新建 Sprint</el-button>
    </div>

    <el-table :data="sprints" border>
      <el-table-column prop="name" label="名称">
        <template #default="{ row }">
          <el-link :underline="false" @click="open(row.id)">{{ row.name }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="start_date" label="开始" width="120" />
      <el-table-column prop="end_date" label="结束" width="120" />
    </el-table>

    <el-dialog v-model="createDialog" title="新建 Sprint" width="440px">
      <el-form label-width="80px">
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="目标"><el-input v-model="form.goal_md" type="textarea" /></el-form-item>
        <el-form-item label="起止">
          <el-date-picker
            v-model="form.range"
            type="daterange"
            value-format="YYYY-MM-DD"
            start-placeholder="开始"
            end-placeholder="结束"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">创建</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailOpen" :title="detail?.name ?? ''" size="46%">
      <template v-if="detail">
        <p class="muted">状态：<el-tag :type="statusType(detail.status)" size="small">{{ detail.status }}</el-tag></p>
        <p v-if="detail.goal_md" class="muted">{{ detail.goal_md }}</p>
        <div v-for="(n, status) in detail.status_counts" :key="status" style="margin-right: 8px">
          <el-tag size="small" style="margin: 2px">{{ status }}: {{ n }}</el-tag>
        </div>

        <el-divider content-position="left">工作项</el-divider>
        <el-table :data="detail.items" size="small" border>
          <el-table-column label="ID" width="110">
            <template #default="{ row }">
              <router-link :to="`/projects/${key}/items/${row.display_id}`">{{ row.display_id }}</router-link>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="标题" />
          <el-table-column prop="status" label="状态" width="120" />
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button
                link
                type="danger"
                :disabled="false"
                @click="removeItem(row.display_id)"
              >移出</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="detail.status !== 'CLOSED'" style="margin-top: 12px">
          <el-input
            v-model="itemRef"
            placeholder="工作项 display_id（如 DEMO-3），回车加入"
            @keyup.enter="addItem"
          >
            <template #append>
              <el-button :loading="saving" @click="addItem">加入</el-button>
            </template>
          </el-input>
          <div style="margin-top: 16px">
            <el-button
              v-if="detail.status === 'PLANNED'"
              type="primary"
              @click="changeStatus('start')"
            >启动</el-button>
            <el-button v-if="detail.status === 'ACTIVE'" type="warning" @click="closeSprint">
              关闭
            </el-button>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../api";
import type { Sprint, SprintDetail } from "../types";

const props = defineProps<{ key: string }>();
const key = props.key;
const loading = ref(false);
const saving = ref(false);
const sprints = ref<Sprint[]>([]);
const createDialog = ref(false);
const detailOpen = ref(false);
const detail = ref<SprintDetail | null>(null);
const itemRef = ref("");
const form = reactive({ name: "", goal_md: "", range: [] as string[] });

function statusType(status: string) {
  return status === "ACTIVE" ? "success" : status === "CLOSED" ? "info" : "warning";
}

async function load() {
  loading.value = true;
  try {
    sprints.value = (await api.get<Sprint[]>(`/projects/${key}/sprints`)).data;
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  form.name = "";
  form.goal_md = "";
  form.range = [];
  createDialog.value = true;
}

async function create() {
  if (!form.name.trim()) return ElMessage.warning("名称必填");
  saving.value = true;
  try {
    await api.post(`/projects/${key}/sprints`, {
      name: form.name,
      goal_md: form.goal_md || null,
      start_date: form.range?.[0] ?? null,
      end_date: form.range?.[1] ?? null,
    });
    createDialog.value = false;
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
  }
}

async function open(id: string) {
  detail.value = (await api.get<SprintDetail>(`/sprints/${id}`)).data;
  detailOpen.value = true;
}

async function refreshDetail() {
  if (detail.value) await open(detail.value.id);
}

async function addItem() {
  if (!detail.value || !itemRef.value.trim()) return;
  try {
    await api.post(`/sprints/${detail.value.id}/items`, { items: [itemRef.value.trim()] });
    itemRef.value = "";
    await Promise.all([refreshDetail(), load()]);
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}

async function removeItem(displayId: string) {
  if (!detail.value) return;
  try {
    await api.del(
      `/sprints/${detail.value.id}/items/${encodeURIComponent(displayId)}`
    );
    await refreshDetail();
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}

async function changeStatus(action: "start") {
  if (!detail.value) return;
  try {
    await api.post(`/sprints/${detail.value.id}/${action}`);
    await Promise.all([refreshDetail(), load()]);
  } catch (e) {
    ElMessage.error((e as Error).message);
  }
}

async function closeSprint() {
  if (!detail.value) return;
  try {
    await ElMessageBox.confirm("关闭后不能再加项；未终态项需先移出。确认关闭？", "关闭 Sprint");
    await api.post(`/sprints/${detail.value.id}/close`);
    await Promise.all([refreshDetail(), load()]);
  } catch (e) {
    if (e !== "cancel") ElMessage.error((e as Error).message);
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
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
