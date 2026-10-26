<template>
  <router-view v-if="isAuthScreen" />
  <el-container v-else style="min-height: 100vh">
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
            <el-badge v-if="who?.unread_count" :value="who.unread_count" :max="99" type="primary" />
          </el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/workspaces`">工作区</el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/members`">成员</el-menu-item>
          <el-menu-item :index="`/projects/${projectKey}/settings`">设置</el-menu-item>
        </template>
      </el-menu>
      <div class="whoami">
        <template v-if="who">
          <span class="who-name">{{ who.member.name }}</span>
          <span v-if="who.project" class="who-project">{{ who.project.key }}</span>
          <el-button link type="primary" @click="onLogout">登出</el-button>
        </template>
      </div>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api } from "./api";
import { logout } from "./auth";
import type { Whoami } from "./types";

const route = useRoute();
const router = useRouter();
const projectKey = computed(() =>
  typeof route.params.key === "string" ? route.params.key : ""
);
const who = ref<Whoami | null>(null);
let timer: number | undefined;

const isAuthScreen = computed(() => route.meta.public === true);

async function loadWhoami() {
  if (isAuthScreen.value) return;
  try {
    who.value = (await api.get<Whoami>("/whoami")).data;
  } catch {
    who.value = null;
  }
}

async function onLogout() {
  await logout();
  router.push("/login");
}

watch(isAuthScreen, loadWhoami);

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
  font-weight: 500;
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
  font-weight: 500;
  color: var(--el-text-color-primary);
}
</style>
