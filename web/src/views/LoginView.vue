<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="never">
      <div class="login-title">rd-manager 登录</div>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="项目 Key">
          <el-input v-model="projectKey" placeholder="RDM" autocomplete="organization" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="name" placeholder="owner" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input
            v-model="password"
            type="password"
            show-password
            autocomplete="current-password"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-button type="primary" class="login-btn" :loading="loading" @click="submit">
          登录
        </el-button>
      </el-form>
      <div class="login-hint">
        初始 owner 密码见 data-dir 下的 <code>bootstrap-password</code>（首次启动生成，0600）。
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { login, rememberedProjectKey, rememberProjectKey } from "../auth";
import { errorCause } from "../api";

const route = useRoute();
const router = useRouter();
const projectKey = ref(rememberedProjectKey());
const name = ref("");
const password = ref("");
const loading = ref(false);

// Server-side (non-SPA) paths the OAuth flow may ask us to return to after
// login: /authorize must be re-requested as a full page (with the new session
// cookie) so the authorization server can continue and redirect to consent.
const SERVER_PATHS = new Set([
  "/authorize",
  "/token",
  "/register",
  "/revoke",
]);

function isSafeInternalPath(target: unknown): target is string {
  return (
    typeof target === "string" &&
    target.startsWith("/") &&
    !target.startsWith("//") &&
    !target.startsWith("/\\")
  );
}

function isServerPath(target: string): boolean {
  const path = target.split("?")[0].split("#")[0];
  return SERVER_PATHS.has(path) || path.startsWith("/.well-known/");
}

async function submit() {
  if (loading.value) return;
  loading.value = true;
  try {
    rememberProjectKey(projectKey.value.trim() || "RDM");
    await login(projectKey.value.trim() || "RDM", name.value.trim(), password.value);
    // OAuth provider redirects to /login?next=/authorize?...; the router guard
    // uses ?redirect= for SPA pages. Honor both.
    const target =
      (route.query.next as string | undefined) ??
      (route.query.redirect as string | undefined);
    if (isSafeInternalPath(target)) {
      if (isServerPath(target)) {
        // Full navigation: re-hit the server endpoint with the session cookie.
        window.location.assign(target);
        return;
      }
      router.push(target);
    } else {
      router.push("/projects");
    }
  } catch (e) {
    ElMessage.error(errorCause(e)?.message || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
}
.login-card {
  width: 360px;
  border-radius: 4px;
}
.login-title {
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 16px;
}
.login-btn {
  width: 100%;
}
.login-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
