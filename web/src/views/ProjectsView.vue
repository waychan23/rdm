<template>
  <div>
    <div class="head">
      <h2>项目</h2>
      <el-button type="primary" @click="dialog = true">新建项目</el-button>
    </div>
    <el-table :data="projects" border>
      <el-table-column prop="key" label="Key" width="120" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="status" label="状态" width="120" />
      <el-table-column label="操作" width="320">
        <template #default="{ row }">
          <el-link :href="`/projects/${row.key}/members`" :underline="false">成员</el-link>
          <el-divider direction="vertical" />
          <el-link :href="`/projects/${row.key}/backlog`" :underline="false">Backlog</el-link>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="新建项目" width="420px">
      <el-form label-width="72px">
        <el-form-item label="Key"><el-input v-model="form.key" placeholder="DEMO" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
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
import { ElMessage } from "element-plus";
import { api } from "../api";
import type { Project } from "../types";

const projects = ref<Project[]>([]);
const dialog = ref(false);
const saving = ref(false);
const form = reactive({ key: "", name: "" });

async function load() {
  projects.value = (await api.get<Project[]>("/projects")).data;
}

async function create() {
  saving.value = true;
  try {
    await api.post("/projects", { key: form.key, name: form.name });
    dialog.value = false;
    form.key = "";
    form.name = "";
    await load();
  } catch (e) {
    ElMessage.error((e as Error).message);
  } finally {
    saving.value = false;
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
</style>
