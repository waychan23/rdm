import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";

import IconButton from "@atlaskit/button/icon/button";
import Badge from "@atlaskit/badge";
import { Box, Inline, Text, xcss } from "@atlaskit/primitives";
import NotificationIcon from "@atlaskit/icon/core/notification";
import GridIcon from "@atlaskit/icon/core/grid";
import BoardIcon from "@atlaskit/icon/core/board";
import BacklogIcon from "@atlaskit/icon/core/backlog";
import CalendarIcon from "@atlaskit/icon/core/calendar";
import EmailIcon from "@atlaskit/icon/core/email";
import FolderIcon from "@atlaskit/icon/core/folder-open";
import PeopleIcon from "@atlaskit/icon/core/people-group";
import SettingsIcon from "@atlaskit/icon/core/settings";
import LogOutIcon from "@atlaskit/icon/core/log-out";

import { api } from "../lib/api";
import { logout } from "../lib/auth";
import { safePostLoginPath } from "../lib/oauth";
import type { Whoami } from "../types";
import "../styles/shell.css";

const topbarStyles = xcss({
  height: "space.600",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  paddingInline: "space.300",
  backgroundColor: "elevation.surface",
  borderBottom: "1px solid",
  borderColor: "color.border",
  flexShrink: 0,
});

const crumbLinkStyles = xcss({
  color: "color.link",
  textDecoration: "none",
  cursor: "pointer",
  fontWeight: "font.weight.medium",
});

const shellStyles = xcss({
  display: "flex",
  flexDirection: "column",
  height: "100vh",
  overflow: "hidden",
  backgroundColor: "elevation.surface",
  color: "color.text",
});

const bodyStyles = xcss({
  display: "flex",
  flex: "1",
  minHeight: "0",
});

const railStyles = xcss({
  width: "space.800",
  backgroundColor: "elevation.surface.sunken",
  borderRight: "1px solid",
  borderColor: "color.border",
  padding: "space.100",
  display: "flex",
  flexDirection: "column",
  gap: "space.050",
  flexShrink: 0,
  overflowY: "auto",
});

const contentStyles = xcss({
  flex: "1",
  minWidth: "0",
  minHeight: "0",
  display: "flex",
  flexDirection: "column",
  overflow: "auto",
});

const bellBadgeStyles = xcss({
  position: "absolute",
  top: "space.050",
  insetInlineEnd: "space.050",
  pointerEvents: "none",
});

const bellWrapperStyles = xcss({
  display: "inline-flex",
  position: "relative",
});

interface NavEntry {
  to: (key: string) => string;
  label: string;
  testId: string;
  icon: (props: { label: string }) => ReactNode;
}

const PROJECT_NAV: NavEntry[] = [
  { to: (k) => `/projects/${k}/board`, label: "看板", testId: "board", icon: BoardIcon },
  { to: (k) => `/projects/${k}/backlog`, label: "工作项", testId: "backlog", icon: BacklogIcon },
  { to: (k) => `/projects/${k}/sprints`, label: "迭代", testId: "sprints", icon: CalendarIcon },
  { to: (k) => `/projects/${k}/mailbox`, label: "信箱", testId: "mailbox", icon: EmailIcon },
  {
    to: (k) => `/projects/${k}/workspaces`,
    label: "工作区",
    testId: "workspaces",
    icon: FolderIcon,
  },
  { to: (k) => `/projects/${k}/members`, label: "成员", testId: "members", icon: PeopleIcon },
  { to: (k) => `/projects/${k}/settings`, label: "设置", testId: "project-settings", icon: SettingsIcon },
];

export default function AppShell() {
  const params = useParams<{ key?: string }>();
  const projectKey = params.key ?? "";
  const navigate = useNavigate();
  const location = useLocation();
  const [who, setWho] = useState<Whoami | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api
        .get<Whoami>("/whoami")
        .then((res) => alive && setWho(res.data))
        .catch(() => alive && setWho(null));
    };
    load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [projectKey]);

  const onLogout = async () => {
    const returnTo = safePostLoginPath(location.pathname + location.search);
    await logout();
    navigate(`/login?redirect=${encodeURIComponent(returnTo)}`);
  };

  return (
    <Box xcss={shellStyles} testId="app-shell">
      <Box as="header" xcss={topbarStyles} testId="app-topbar">
        <Inline space="space.100" alignBlock="center">
          <Link to="/projects" data-testid="topbar-home">
            <Box xcss={crumbLinkStyles}>rdm</Box>
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
          <Box xcss={bellWrapperStyles}>
            <IconButton
              icon={(iconProps) => <NotificationIcon {...iconProps} spacing="spacious" />}
              label="信箱"
              appearance="subtle"
              testId="topbar-mailbox"
              onClick={() => projectKey && navigate(`/projects/${projectKey}/mailbox`)}
            />
            {who?.unread_count ? (
              <Box xcss={bellBadgeStyles}>
                <Badge appearance="danger">{who.unread_count}</Badge>
              </Box>
            ) : null}
          </Box>
          <Text color="color.text.subtle" testId="topbar-current-user">
            {who
              ? who.identity.act_as
                ? `${who.identity.name}（以 ${who.user.name} 身份）`
                : who.user.name
              : "—"}
          </Text>
          <IconButton
            icon={(iconProps) => <LogOutIcon {...iconProps} />}
            label="登出"
            appearance="subtle"
            testId="topbar-logout"
            onClick={onLogout}
          />
        </Inline>
      </Box>

      <Box xcss={bodyStyles}>
        <Box as="nav" xcss={railStyles} aria-label="主导航" testId="app-sidebar">
          <RailItem to="/projects" label="项目" testId="projects" icon={GridIcon} end />
          {(who?.org_roles.includes("org_owner") ||
            who?.org_roles.includes("user_manager")) && (
            <RailItem to="/org/users" label="用户" testId="org-users" icon={PeopleIcon} />
          )}
          <RailItem to="/settings" label="我的" testId="settings" icon={SettingsIcon} end />
          {projectKey &&
            PROJECT_NAV.map((entry) => (
              <RailItem
                key={entry.label}
                to={entry.to(projectKey)}
                label={entry.label}
                testId={`project-${entry.testId}`}
                icon={entry.icon}
              />
            ))}
        </Box>
        <Box as="main" xcss={contentStyles} testId="app-content">
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
      <Text size="small" color="inherit">
        {label}
      </Text>
    </NavLink>
  );
}
