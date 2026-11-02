import { useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import IconButton from "@atlaskit/button/icon/button";
import Badge from "@atlaskit/badge";
import { Box, Inline, Text } from "@atlaskit/primitives/compiled";

import TruncatedText from "../components/TruncatedText";
import NotificationIcon from "@atlaskit/icon/core/notification";
import SearchIcon from "@atlaskit/icon/core/search";
import InboxIcon from "@atlaskit/icon/core/inbox";
import GridIcon from "@atlaskit/icon/core/grid";
import BoardIcon from "@atlaskit/icon/core/board";
import BacklogIcon from "@atlaskit/icon/core/backlog";
import BugIcon from "@atlaskit/icon/core/bug";
import CalendarIcon from "@atlaskit/icon/core/calendar";
import ReleaseIcon from "@atlaskit/icon/core/release";
import EmailIcon from "@atlaskit/icon/core/email";
import FolderIcon from "@atlaskit/icon/core/folder-open";
import PeopleIcon from "@atlaskit/icon/core/people-group";
import SettingsIcon from "@atlaskit/icon/core/settings";
import LogOutIcon from "@atlaskit/icon/core/log-out";
import BranchIcon from "@atlaskit/icon/core/branch";
import { token } from "@atlaskit/tokens";

import LocaleSwitcher from "../components/LocaleSwitcher";
import { logout, refreshSession, useCurrentUser } from "../lib/auth";
import { safePostLoginPath } from "../lib/oauth";
import { startEventStream } from "../lib/stream";
import { userLabel } from "../lib/users";
import {
  subscribeViewMemory,
  viewMemoryVersion,
  viewPath,
  type WorkView,
} from "../workitems/viewMemory";
import "../styles/shell.css";

const styles = cssMap({
  topbar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    paddingInline: "var(--ds-space-300)",
    backgroundColor: "var(--ds-surface)",
    flexShrink: 0,
  },
  crumbLink: {
    color: "var(--ds-link)",
    textDecoration: "none",
    cursor: "pointer",
    fontWeight: "var(--ds-font-weight-medium)",
  },
  userLink: {
    display: "inline-flex",
    alignItems: "center",
    paddingBlock: "var(--ds-space-025)",
    paddingInline: "var(--ds-space-075)",
    borderRadius: "var(--ds-radius-small)",
    "&:hover": {
      backgroundColor: "var(--ds-background-neutral-subtle-hovered)",
    },
  },
  shell: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    overflow: "hidden",
    backgroundColor: "var(--ds-surface)",
    color: "var(--ds-text)",
  },
  body: {
    display: "flex",
    flex: "1",
    minHeight: "0",
  },
  content: {
    position: "relative",
    flex: "1",
    minWidth: "0",
    minHeight: "0",
    display: "flex",
    flexDirection: "column",
    overflow: "auto",
  },
  bellBadge: {
    position: "absolute",
    top: "var(--ds-space-050)",
    insetInlineEnd: "var(--ds-space-050)",
    pointerEvents: "none",
  },
  bellWrapper: {
    display: "inline-flex",
    position: "relative",
  },
});

type NavKey =
  | "project.board"
  | "project.backlog"
  | "project.issues"
  | "project.sprints"
  | "project.releases"
  | "project.mailbox"
  | "project.workspaces"
  | "project.members"
  | "project.settings";

interface NavEntry {
  to: (key: string) => string;
  labelKey: NavKey;
  testId: string;
  icon: (props: { label: string }) => ReactNode;
  /** Work item pages re-open with their remembered filters (RDM-80). */
  view?: WorkView;
}

const PROJECT_NAV: NavEntry[] = [
  { to: (k) => `/projects/${k}/board`, view: "board", labelKey: "project.board", testId: "board", icon: BoardIcon },
  { to: (k) => `/projects/${k}/backlog`, view: "backlog", labelKey: "project.backlog", testId: "backlog", icon: BacklogIcon },
  { to: (k) => `/projects/${k}/issues`, view: "issues", labelKey: "project.issues", testId: "issues", icon: BugIcon },
  { to: (k) => `/projects/${k}/sprints`, labelKey: "project.sprints", testId: "sprints", icon: CalendarIcon },
  { to: (k) => `/projects/${k}/releases`, labelKey: "project.releases", testId: "releases", icon: ReleaseIcon },
  { to: (k) => `/projects/${k}/mailbox`, labelKey: "project.mailbox", testId: "mailbox", icon: EmailIcon },
  {
    to: (k) => `/projects/${k}/workspaces`,
    labelKey: "project.workspaces",
    testId: "workspaces",
    icon: FolderIcon,
  },
  { to: (k) => `/projects/${k}/members`, labelKey: "project.members", testId: "members", icon: PeopleIcon },
  { to: (k) => `/projects/${k}/settings`, labelKey: "project.settings", testId: "project-settings", icon: SettingsIcon },
];

export default function AppShell() {
  const params = useParams<{ key?: string }>();
  const projectKey = params.key ?? "";
  const navigate = useNavigate();
  const location = useLocation();
  const who = useCurrentUser();
  const { t } = useTranslation("nav");
  // Recompute the work item nav targets whenever a page remembers new filters
  // (RDM-80 keepalive / board-list sync).
  const viewMemory = useSyncExternalStore(
    subscribeViewMemory,
    viewMemoryVersion,
    viewMemoryVersion,
  );
  const projectNav = useMemo(
    () =>
      PROJECT_NAV.map((entry) => ({
        ...entry,
        href: entry.view ? viewPath(projectKey, entry.view) : entry.to(projectKey),
      })),
    [projectKey, viewMemory],
  );

  useEffect(() => {
    void refreshSession();
    const timer = window.setInterval(() => void refreshSession(), 60_000);
    return () => window.clearInterval(timer);
  }, [projectKey]);

  useEffect(() => {
    const stop = startEventStream((event) => {
      if (event.event === "notification.created") {
        void refreshSession();
        window.dispatchEvent(new CustomEvent("rdm:notification", { detail: event.data }));
      } else if (event.event === "work_item.changed" || event.event === "comment.changed") {
        window.dispatchEvent(new CustomEvent("rdm:data-changed", { detail: event.data }));
      }
    });
    return stop;
  }, []);

  const unreadCount = projectKey
    ? (who?.projects.find((p) => p.key === projectKey)?.unread_count ?? 0)
    : (who?.unread_count ?? 0);
  const notificationUnread = who?.notification_unread_count ?? 0;

  const onLogout = async () => {
    const returnTo = safePostLoginPath(location.pathname + location.search);
    await logout();
    navigate(`/login?redirect=${encodeURIComponent(returnTo)}`);
  };

  return (
    <Box xcss={styles.shell} testId="app-shell">
      {/* cssMap's height type only accepts raw dimensions, so the topbar height
          is applied as the spacing token at runtime. */}
      <Box
        as="header"
        xcss={styles.topbar}
        style={{ height: token("space.600"), borderBlockEnd: `1px solid ${token("color.border")}` }}
        testId="app-topbar"
      >
        <Inline space="space.100" alignBlock="center">
          <Link to="/projects" data-testid="topbar-home">
            <Box xcss={styles.crumbLink}>rdm</Box>
          </Link>
          {projectKey && (
            <>
              <Text color="color.text.subtlest">/</Text>
              <Text color="color.text.subtlest" testId="topbar-project-key">
                {projectKey}
              </Text>
            </>
          )}
        </Inline>
        <Inline space="space.150" alignBlock="center">
          <IconButton
            icon={(iconProps) => <SearchIcon {...iconProps} />}
            label={t("topbar.search")}
            appearance="subtle"
            testId="topbar-search"
            onClick={() => navigate("/search")}
          />
          <Box xcss={styles.bellWrapper}>
            <IconButton
              icon={(iconProps) => <InboxIcon {...iconProps} spacing="spacious" />}
              label={t("topbar.notifications")}
              appearance="subtle"
              testId="topbar-inbox"
              onClick={() => navigate("/inbox")}
            />
            {notificationUnread > 0 ? (
              <Box xcss={styles.bellBadge}>
                <Badge appearance="danger">{notificationUnread}</Badge>
              </Box>
            ) : null}
          </Box>
          <Box xcss={styles.bellWrapper}>
            <IconButton
              icon={(iconProps) => <NotificationIcon {...iconProps} spacing="spacious" />}
              label={t("topbar.mailbox")}
              appearance="subtle"
              testId="topbar-mailbox"
              onClick={() =>
                navigate(projectKey ? `/projects/${projectKey}/mailbox` : "/mailbox")
              }
            />
            {unreadCount > 0 ? (
              <Box xcss={styles.bellBadge}>
                <Badge appearance="danger">{unreadCount}</Badge>
              </Box>
            ) : null}
          </Box>
          <LocaleSwitcher />
          <Link to="/settings" className="rdm-topbar-user" data-testid="topbar-current-user">
            <Box xcss={styles.userLink}>
              <Text color="color.text.subtle">
                {who
                  ? who.identity.act_as
                    ? t("topbar.actingAs", {
                        identity: userLabel(who.identity),
                        user: userLabel(who.user),
                      })
                    : userLabel(who.user)
                  : "—"}
              </Text>
            </Box>
          </Link>
          <IconButton
            icon={(iconProps) => <LogOutIcon {...iconProps} />}
            label={t("topbar.logout")}
            appearance="subtle"
            testId="topbar-logout"
            onClick={onLogout}
          />
        </Inline>
      </Box>

      <Box xcss={styles.body}>
        <nav className="rdm-rail" aria-label={t("rail.main")} data-testid="app-sidebar">
          <div className="rdm-rail-group" data-testid="rail-group-org">
            <RailItem to="/projects" label={t("rail.projects")} testId="projects" icon={GridIcon} end />
            <RailItem to="/inbox" label={t("rail.inbox")} testId="inbox" icon={InboxIcon} />
            {(who?.org_roles.includes("org_owner") ||
              who?.org_roles.includes("user_manager")) && (
              <RailItem to="/org/users" label={t("rail.orgUsers")} testId="org-users" icon={PeopleIcon} />
            )}
            {(who?.org_roles.includes("org_owner") ||
              who?.org_roles.includes("user_manager")) && (
              <RailItem to="/workflow-configs" label={t("rail.workflows")} testId="workflow-configs" icon={BranchIcon} />
            )}
            <RailItem to="/settings" label={t("rail.settings")} testId="settings" icon={SettingsIcon} end />
          </div>
          {projectKey && (
            <>
              <div
                className="rdm-rail-divider"
                role="separator"
                aria-orientation="horizontal"
                data-testid="rail-divider"
              />
              <div className="rdm-rail-group" data-testid="rail-group-project" data-project={projectKey}>
                {projectNav.map((entry) => (
                  <RailItem
                    key={entry.labelKey}
                    to={entry.href}
                    label={t(entry.labelKey)}
                    testId={`project-${entry.testId}`}
                    icon={entry.icon}
                  />
                ))}
              </div>
            </>
          )}
        </nav>
        <Box as="main" xcss={styles.content} testId="app-content">
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}

function RailItem({
  to,
  label,
  testId,
  icon: Icon,
  end,
}: {
  to: string;
  label: string;
  testId: string;
  icon: (props: { label: string }) => ReactNode;
  end?: boolean;
}) {
  return (
    <NavLink to={to} end={end} className="rdm-rail-item" data-testid={`rail-item-${testId}`}>
      <Icon label={label} />
      <TruncatedText className="rdm-rail-label" text={label} />
    </NavLink>
  );
}
