import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";

import IconButton from "@atlaskit/button/icon/button";
import Badge from "@atlaskit/badge";
import { token } from "@atlaskit/tokens";
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
import ArrowOutIcon from "@atlaskit/icon/core/arrow-left";

import { api } from "../lib/api";
import { logout } from "../lib/auth";
import type { Whoami } from "../types";

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

const bodyStyles = xcss({
  display: "flex",
  minHeight: "calc(100vh - space.600)",
});

const railStyles = xcss({
  width: "space.800",
  backgroundColor: "color.background.neutral.subtle",
  borderRight: "1px solid",
  borderColor: "color.border",
  paddingBlockStart: "space.100",
  flexShrink: 0,
});

// NavLink renders an inline <a> and does not accept the xcss prop, so size
// and color it directly (all values come from tokens).
const railItemStyle = (isActive: boolean): CSSProperties => ({
  display: "flex",
  width: "100%",
  height: token("space.600"),
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  gap: token("space.025"),
  textDecoration: "none",
  backgroundColor: isActive ? token("color.background.selected") : undefined,
  color: isActive ? token("color.text.selected") : token("color.text.subtlest"),
});

const bellBadgeStyles = xcss({
  position: "absolute",
  top: "space.050",
  insetInlineEnd: "space.050",
  pointerEvents: "none",
});

const bellWrapperStyles0 = xcss({
  display: "inline-flex",
  position: "relative",
});

interface NavEntry {
  to: (key: string) => string;
  label: string;
  icon: (props: { label: string }) => ReactNode;
}

const PROJECT_NAV: NavEntry[] = [
  { to: (k) => `/projects/${k}/board`, label: "看板", icon: BoardIcon },
  { to: (k) => `/projects/${k}/backlog`, label: "工作项", icon: BacklogIcon },
  { to: (k) => `/projects/${k}/sprints`, label: "迭代", icon: CalendarIcon },
  { to: (k) => `/projects/${k}/mailbox`, label: "信箱", icon: EmailIcon },
  { to: (k) => `/projects/${k}/workspaces`, label: "工作区", icon: FolderIcon },
  { to: (k) => `/projects/${k}/members`, label: "成员", icon: PeopleIcon },
  { to: (k) => `/projects/${k}/settings`, label: "设置", icon: SettingsIcon },
];

export default function AppShell() {
  const params = useParams<{ key?: string }>();
  const projectKey = params.key ?? "";
  const navigate = useNavigate();
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
    await logout();
    navigate("/login");
  };

  return (
    <Box xcss={shellStyles}>
      <Box as="header" xcss={topbarStyles}>
        <Inline space="space.100" alignBlock="center">
          <Link to="/projects">
            <Box xcss={crumbLinkStyles}>rdm</Box>
          </Link>
          {projectKey && (
            <>
              <Text color="color.text.subtlest">/</Text>
              <Text color="color.text.subtlest">{projectKey}</Text>
            </>
          )}
        </Inline>
        <Inline space="space.150" alignBlock="center">
          <Box xcss={bellWrapperStyles0}>
            <IconButton
              icon={(iconProps) => <NotificationIcon {...iconProps} spacing="spacious" />}
              label="信箱"
              appearance="subtle"
              onClick={() => projectKey && navigate(`/projects/${projectKey}/mailbox`)}
            />
            {who?.unread_count ? (
              <Box xcss={bellBadgeStyles}>
                <Badge appearance="danger">{who.unread_count}</Badge>
              </Box>
            ) : null}
          </Box>
          <Text color="color.text.subtle">
            {who
              ? who.identity.act_as
                ? `${who.identity.name}（以 ${who.user.name} 身份）`
                : who.user.name
              : "—"}
          </Text>
          <IconButton
            icon={(iconProps) => <ArrowOutIcon {...iconProps} />}
            label="登出"
            appearance="subtle"
            onClick={onLogout}
          />
        </Inline>
      </Box>

      <Box xcss={bodyStyles}>
        <Box as="nav" xcss={railStyles} aria-label="主导航">
          <RailItem to="/projects" label="项目" icon={GridIcon} end />
          {(who?.org_roles.includes("org_owner") ||
            who?.org_roles.includes("user_manager")) && (
            <RailItem to="/org/users" label="用户" icon={PeopleIcon} />
          )}
          <RailItem to="/settings" label="我的" icon={SettingsIcon} end />
          {projectKey &&
            PROJECT_NAV.map((entry) => (
              <RailItem
                key={entry.label}
                to={entry.to(projectKey)}
                label={entry.label}
                icon={entry.icon}
              />
            ))}
        </Box>
        <Box as="main" xcss={contentStyles}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}

const shellStyles = xcss({
  minHeight: "100vh",
  backgroundColor: "elevation.surface",
  color: "color.text",
});

const contentStyles = xcss({
  flex: 1,
  minWidth: "0",
});

function RailItem({
  to,
  label,
  icon: Icon,
  end,
}: {
  to: string;
  label: string;
  icon: (props: { label: string }) => ReactNode;
  end?: boolean;
}) {
  return (
    <NavLink to={to} end={end} style={({ isActive }) => railItemStyle(isActive)}>
      <Icon label={label} />
      <Text size="small" color="inherit">
        {label}
      </Text>
    </NavLink>
  );
}
