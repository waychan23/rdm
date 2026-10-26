<template>
  <div class="page">
    <header class="page-header">
      <div class="page-title">项目</div>
      <el-button size="small" type="primary" @click="dialog = true">新建项目</el-button>
    </header>

    <div class="cards">
      <div v-for="p in projects" :key="p.id" class="card" @click="open(p)">
        <div class="card-title">{{ p.name }}</div>
        <div class="card-meta">
          <span class="key rdm-num">{{ p.key }}</span>
          <el-tag size="small" :type="p.status === 'archived' ? 'info' : 'success'">
            {{ p.status === "archived" ? "已归档" : "进行中" }}
          </el-tag>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialog" title="新建项目" width="420px">
      <el-form label-position="top">
        <el-form-item label="Key"><el-input v-model="form.key" placeholder="DEMO" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description_md" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="create">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { api, errorCause } from "../api";
import type { Project } from "../types";

const router = useRouter();
const projects = ref<Project[]>([]);
const dialog = ref(false);
const saving = ref(false);
const form = reactive({ key: "", name: "", description_md: "" });

async function load() {
  projects.value = (await api.get<Project[]>("/projects")).data;
}
function open(p: Project) {
  router.push(`/projects/${p.key}`);
}
async function create() {
  saving.value = true;
  try {
    await api.post("/projects", { ...form });
    dialog.value = false;
    form.key = form.name = form.description_md = "";
    await load();
  } catch (e) {
    ElMessage.error(errorCause(e)?.message || "创建失败");
  } finally {
    saving.value = false;
  }
}
onMounted(load);
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
  color: var(--rdm-text-1);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--rdm-gutter);
}
.card {
  border: 1px solid var(--rdm-border);
  border-radius: var(--rdm-radius-2);
  padding: var(--rdm-space-5);
  cursor: pointer;
  background: var(--rdm-surface);
}
.card:hover {
  border-color: var(--rdm-border-strong);
  background: var(--rdm-surface-subtle);
}
.card-title {
  font: var(--rdm-type-card-title);
  color: var(--rdm-text-1);
  margin-bottom: var(--rdm-space-3);
}
.card-meta {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-3);
}
.key {
  font: var(--rdm-type-meta);
  color: var(--rdm-accent-strong);
}
</style>
