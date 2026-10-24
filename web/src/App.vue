<template>
  <el-container style="min-height: 100vh">
    <el-header class="topbar">
      <div class="brand">rd-manager</div>
      <el-menu mode="horizontal" :router="true" :default-active="$route.path" :ellipsis="false">
        <el-menu-item index="/projects">项目</el-menu-item>
      </el-menu>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup lang="ts"></script>

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
}
</style>
