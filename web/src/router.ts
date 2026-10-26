import { createRouter, createWebHistory } from "vue-router";
import ProjectsView from "./views/ProjectsView.vue";
import MembersView from "./views/MembersView.vue";
import BacklogView from "./views/BacklogView.vue";
import BoardView from "./views/BoardView.vue";
import SprintsView from "./views/SprintsView.vue";
import MailboxView from "./views/MailboxView.vue";
import WorkspacesView from "./views/WorkspacesView.vue";
import SettingsView from "./views/SettingsView.vue";
import ItemView from "./views/ItemView.vue";
import LoginView from "./views/LoginView.vue";
import ConsentView from "./views/ConsentView.vue";
import { ensureSession } from "./auth";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", component: LoginView, meta: { public: true } },
    { path: "/oauth/consent/:id", component: ConsentView, meta: { bare: true } },
    { path: "/", redirect: "/projects" },
    { path: "/projects", component: ProjectsView },
    { path: "/projects/:key/board", component: BoardView, props: true },
    { path: "/projects/:key/backlog", component: BacklogView, props: true },
    { path: "/projects/:key/sprints", component: SprintsView, props: true },
    { path: "/projects/:key/mailbox", component: MailboxView, props: true },
    { path: "/projects/:key/workspaces", component: WorkspacesView, props: true },
    { path: "/projects/:key/members", component: MembersView, props: true },
    { path: "/projects/:key/settings", component: SettingsView, props: true },
    {
      path: "/projects/:key/items/:id",
      component: ItemView,
      props: true,
    },
  ],
});

router.beforeEach(async (to) => {
  if (to.meta.public) return true;
  const member = await ensureSession();
  if (!member) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  return true;
});
