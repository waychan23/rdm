<template>
  <router-view v-if="isBare" />
  <div v-else class="shell">
    <header class="topbar">
      <div class="crumb">
        <span class="crumb-root" @click="goProjects">rdm</span>
        <template v-if="projectKey">
          <span class="crumb-sep">/</span>
          <span class="crumb-project">{{ projectKey }}</span>
        </template>
      </div>
      <div class="topbar-right">
        <el-badge v-if="who?.unread_count" :value="who.unread_count" :max="99" type="danger">
          <el-button text :icon="Bell" @click="goMailbox" />
        </el-badge>
        <el-button v-else text :icon="Bell" @click="goMailbox" />
        <span class="who-name">{{ who?.member.name ?? "—" }}</span>
        <el-button link type="primary" :icon="SwitchButton" @click="onLogout">登出</el-button>
      </div>
    </header>
    <div class="body">
      <nav class="rail">
        <RouterLink class="rail-item" :class="{ active: isActive('/projects') }" to="/projects">
          <el-icon :size="20"><Grid /></el-icon>
          <span>项目</span>
        </RouterLink>
        <template v-if="projectKey">
          <RouterLink
            v-for="item in nav"
            :key="item.to"
            class="rail-item"
            :class="{ active: isActive(item.to) }"
            :to="item.to"
          >
            <el-icon :size="20"><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
          </RouterLink>
        </template>
      </nav>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Bell,
  Calendar,
  ChatDotRound,
  FolderOpened,
  Grid,
  List,
  Setting,
  SwitchButton,
  User,
} from "@element-plus/icons-vue";
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

const base = () => `/projects/${projectKey.value}`;
const nav = computed(() => [
  { to: `${base()}/board`, icon: Calendar, label: "看板" },
  { to: `${base()}/backlog`, icon: List, label: "工作项" },
  { to: `${base()}/sprints`, icon: Calendar, label: "迭代" },
  { to: `${base()}/mailbox`, icon: ChatDotRound, label: "信箱" },
  { to: `${base()}/workspaces`, icon: FolderOpened, label: "工作区" },
  { to: `${base()}/members`, icon: User, label: "成员" },
  { to: `${base()}/settings`, icon: Setting, label: "设置" },
]);

const isBare = computed(() => route.meta.public === true || route.meta.bare === true);

function isActive(path: string) {
  return route.path === path || route.path.startsWith(path + "/");
}
function goProjects() {
  router.push("/projects");
}
function goMailbox() {
  if (projectKey.value) router.push(`${base()}/mailbox`);
}

async function loadWhoami() {
  if (isBare.value) return;
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

onMounted(() => {
  loadWhoami();
  timer = window.setInterval(loadWhoami, 60_000);
});
onUnmounted(() => window.clearInterval(timer));
</script>

<style scoped>
.shell {
  min-height: 100vh;
  background: var(--rdm-surface);
}
.topbar {
  height: var(--rdm-topbar-h);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--rdm-space-8);
  background: var(--rdm-surface);
  border-bottom: 1px solid var(--rdm-border);
}
.crumb {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-2);
  font: var(--rdm-type-body);
}
.crumb-root {
  color: var(--rdm-accent-strong);
  cursor: pointer;
}
.crumb-sep,
.crumb-project {
  color: var(--rdm-text-2);
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--rdm-space-3);
}
.who-name {
  font: var(--rdm-type-meta);
  color: var(--rdm-text-2);
}
.body {
  display: flex;
  min-height: calc(100vh - var(--rdm-topbar-h));
}
.rail {
  width: var(--rdm-rail-w);
  background: var(--rdm-surface-subtle);
  border-right: 1px solid var(--rdm-border);
  padding-top: var(--rdm-space-2);
  flex-shrink: 0;
}
.rail-item {
  height: var(--rdm-rail-item-h);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: var(--rdm-text-2);
  text-decoration: none;
  font: var(--rdm-type-meta);
}
.rail-item.active {
  color: var(--rdm-accent-strong);
  background: var(--rdm-surface-selected);
}
.content {
  flex: 1;
  min-width: 0;
}
</style>
