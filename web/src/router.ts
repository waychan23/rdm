import { createRouter, createWebHistory } from "vue-router";
import ProjectsView from "./views/ProjectsView.vue";
import MembersView from "./views/MembersView.vue";
import BacklogView from "./views/BacklogView.vue";
import ItemView from "./views/ItemView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/projects" },
    { path: "/projects", component: ProjectsView },
    { path: "/projects/:key/members", component: MembersView },
    { path: "/projects/:key/backlog", component: BacklogView },
    {
      path: "/projects/:key/items/:id",
      component: ItemView,
      props: true,
    },
  ],
});
