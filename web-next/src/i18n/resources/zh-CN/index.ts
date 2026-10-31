import projects from "./projects";
import releases from "./releases";
import sprints from "./sprints";
import inbox from "./inbox";
import mailbox from "./mailbox";
import members from "./members";
import org from "./org";
import item from "./item";
import admin from "./admin";
import auth from "./auth";
import collab from "./collab";
import common from "./common";
import components from "./components";
import labels from "./labels";
import nav from "./nav";
import workitems from "./workitems";

export const zhCN = {
  common,
  nav,
  labels,
  auth,
  workitems,
  collab,
  admin,
  components,
  projects,
  sprints,
  releases,
  inbox,
  mailbox,
  members,
  org,
  item,
};

export type Resources = typeof zhCN;
