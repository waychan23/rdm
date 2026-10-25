<template>
  <el-container style="min-height: 100vh">
    <el-header class="topbar">
      <div class="brand">rd-manager</div>
      <el-menu mode="horizontal" :router="true" :default-active="$route.path" :ellipsis="false">
        <el-menu-item index="/projects">项目</el-menu-item>
        <template v-if="projectKey">
          <el-menu-item :index="`/projects/${projectKey}/board`">看板</el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/backlog`">Backlog</el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/sprints`">Sprint</el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/mailbox`">
            信箱
            <el-badge v-if="who?.unread_count" :value="who.unread_count" :max="99" type="danger" />
          </el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/workspaces`">工作区</el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/members`">成员</el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/settings`">设置</el-menu-item>
        </template>
      </el-menu>
      <div v-if="who" class="whoami" title="回环访问以 owner 身份执行">
        <el-tag size="small" type="info">回环 owner</el-tag>
        <span class="who-name">{{ who.member.name }}</span>
        <span v-if="who.project" class="who-project">{{ who.project.key }}</span>
      </div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import { api } from "./api";
import type { Whoami } from "./types";

const route = useRoute();
const projectKey = computed(() =>
  typeof route.params.key === "string" ? route.params.key : ""
);
const who = ref<Whoami | null>(null);
let timer: number | undefined;

async function loadWhoami() {
  try {
    who.value = (await api.get<Whoami>("/whoami")).data;
  } catch {
    // identity chip is best-effort; pages show their own errors
  }
}

onMounted(() => {
  loadWhoami();
  timer = window.setInterval(loadWhoami, 60_000);
});
onUnmounted(() => window.clearInterval(timer));
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
  border-bottom: 1px solid var(--el-border-color);
}
.brand {
  font-weight: 700;
  font-size: 18px;
  white-space: nowrap;
}
.whoami {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  white-space: nowrap;
}
.who-name {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>
