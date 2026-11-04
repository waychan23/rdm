import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import { cssMap } from "@atlaskit/css";
import Drawer from "@atlaskit/drawer";
import EmptyState from "@atlaskit/empty-state";
import Heading from "@atlaskit/heading";
import Lozenge, { type NewLozengeProps } from "@atlaskit/lozenge";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";
import { token } from "@atlaskit/tokens";

import ConfirmDialog from "../components/ConfirmDialog";
import ErrorState from "../components/ErrorState";
import ImagePreviewDialog from "../components/ImagePreviewDialog";
import MarkdownText from "../components/MarkdownText";
import { Page, PageHeader } from "../components/Page";
import TextButton from "../components/TextButton";
import TruncatedText from "../components/TruncatedText";
import TypeKindIcon from "../components/TypeKindIcon";
import WorkItemPickerDialog from "../components/WorkItemPickerDialog";
import { useAsync } from "../hooks/useAsync";
import { useEventInstanceId } from "../hooks/useEventBus";
import { useWorkItemUpdatedRefresh } from "../hooks/useWorkItemEvents";
import {
  addReleaseItems,
  cancelRelease as cancelReleaseRequest,
  createRelease,
  getReleaseDetail,
  listProjectReleases,
  publishRelease,
  removeReleaseItem,
  updateRelease,
} from "../api/releases-api";
import { errorCause } from "../lib/api";
import { recallDetail, rememberDetail } from "../lib/detailCache";
import { useNotify } from "../lib/flags";
import { formatDate } from "../lib/format";
import { allowDrawerEnter, suppressDrawerEnter } from "../lib/drawerMotion";
import { useItemOverlayOpen } from "../lib/itemOverlayVisibility";
import { useOpenWorkItem } from "../lib/itemOverlay";
import {
  useListOrigin,
  useListProjectKey,
  useListSearchParams,
} from "../lib/originSearch";
import type { ReleaseDetail, ReleaseStats, WorkItem } from "../types";
import StatusLozenge from "../workitems/status";
import ReleaseFormDialog, { type ReleaseFormValues } from "./releases/ReleaseFormDialog";
import "../styles/table.css";

const centeredRow = { display: "flex", justifyContent: "center" } as const;

const styles = cssMap({
  loading: { padding: "var(--ds-space-400)" },
  detail: { padding: "var(--ds-space-300)" },
  listHeading: {
    flexShrink: 0,
    paddingInline: "var(--ds-space-300)",
    paddingBlockEnd: "var(--ds-space-100)",
  },
  emptyList: {
    paddingInline: "var(--ds-space-300)",
  },
});

function ReleaseStatusLozenge({ status }: { status: string }) {
  const { t } = useTranslation("releases");
  const appearance: NewLozengeProps["appearance"] =
    status === "RELEASED" ? "success" : status === "CANCELLED" ? "default" : "inprogress";
  return (
    <Lozenge appearance={appearance} testId={`release-status-${status}`}>
      {t(`status.${status}`, { defaultValue: status })}
    </Lozenge>
  );
}

function ReleaseProgress({ stats, label }: { stats: ReleaseStats; label: string }) {
  const { t } = useTranslation("releases");
  return (
    <Stack space="space.050">
      <Text size="small">
        {t("progress", { done: stats.done, total: stats.total, percent: stats.percent })}
      </Text>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={stats.percent}
        style={{
          height: token("space.075"),
          borderRadius: token("radius.xsmall"),
          backgroundColor: token("color.background.neutral"),
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${stats.percent}%`,
            height: "100%",
            backgroundColor:
              stats.percent === 100
                ? token("color.background.success.bold")
                : token("color.background.brand.bold"),
          }}
        />
      </div>
    </Stack>
  );
}

export default function ReleasesPage() {
  const { t } = useTranslation("releases");
  const { key: routeKey = "" } = useParams();
  // The origin URL owns the project while this page is a drawer backdrop.
  const projectKey = useListProjectKey(routeKey);
  const openWorkItem = useOpenWorkItem();
  // As a drawer backdrop, the work item drawer owns focus and Escape; the
  // release drawer only needs to stay visible underneath it.
  const isBackdrop = useListOrigin() !== null;
  const notify = useNotify();
  const [searchParams, setSearchParams] = useListSearchParams();
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  // URL-backed so the open detail drawer survives becoming the item drawer's
  // backdrop (opening a work item must not close the release drawer).
  const detailId = searchParams.get("release");
  const setDetailId = (id: string | null) => {
    allowDrawerEnter("release");
    const next = new URLSearchParams(searchParams);
    if (id) next.set("release", id);
    else next.delete("release");
    setSearchParams(next, { replace: true });
  };
  const [detail, setDetail] = useState<ReleaseDetail | null>(() =>
    detailId ? recallDetail<ReleaseDetail>(`release:${detailId}`) : null,
  );
  const [pickerOpen, setPickerOpen] = useState(false);
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadReleases = useCallback(
    () => listProjectReleases(projectKey),
    [projectKey],
  );
  const { data: releases, loading, error, reload } = useAsync(loadReleases, [projectKey]);

  const openDetail = (id: string) => setDetailId(id);

  // Load (or clear) the drawer body whenever the URL-backed selection changes,
  // including when this page is re-created as another item's backdrop.
  useEffect(() => {
    if (!detailId) {
      setDetail(null);
      return;
    }
    // Re-mounts start from the cached payload so the drawer never renders
    // empty for a frame before the fetch resolves.
    setDetail(recallDetail<ReleaseDetail>(`release:${detailId}`));
    let alive = true;
    getReleaseDetail(detailId)
      .then((release) => {
        if (alive) {
          rememberDetail(`release:${detailId}`, release);
          setDetail(release);
        }
      })
      .catch((e) => {
        if (alive) notify.error(t("loadFailed"), errorCause(e)?.message);
      });
    return () => {
      alive = false;
    };
  }, [detailId, notify, t]);

  const refreshDetail = useCallback(async () => {
    if (detailId) {
      const detail = await getReleaseDetail(detailId);
      rememberDetail(`release:${detailId}`, detail);
      setDetail(detail);
    }
  }, [detailId]);

  // RDM-150: refresh the drawer scope after work items changed in a drawer
  // opened above it (keep events while covered).
  const eventInstanceId = useEventInstanceId();
  const overlayOpen = useItemOverlayOpen();
  useWorkItemUpdatedRefresh({
    instanceId: eventInstanceId,
    visible: !overlayOpen,
    matches: (event) =>
      event.projectKey === projectKey &&
      (detail?.items?.some((item) => item.id === event.workItemId) ?? false),
    onRefresh: () => {
      void refreshDetail();
      reload();
    },
  });

  const create = async (values: ReleaseFormValues) => {
    try {
      await createRelease(projectKey, values);
      setShowCreate(false);
      await reload();
    } catch (e) {
      notify.error(t("createFailed"), errorCause(e)?.message);
    }
  };

  const saveEdit = async (values: ReleaseFormValues) => {
    if (!detail) return;
    try {
      await updateRelease(detail.id, values);
      setShowEdit(false);
      await Promise.all([refreshDetail(), reload()]);
      notify.success(t("saveSuccess"));
    } catch (e) {
      notify.error(t("saveFailed"), errorCause(e)?.message);
    }
  };

  const addItems = async (items: WorkItem[]) => {
    if (!detail || items.length === 0 || busy) return;
    setBusy(true);
    try {
      await addReleaseItems(
        detail.id,
        items.map((item) => item.display_id),
      );
      setPickerOpen(false);
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error(t("addFailed"), errorCause(e)?.message);
    } finally {
      setBusy(false);
    }
  };

  const removeItem = async (displayId: string) => {
    if (!detail) return;
    try {
      await removeReleaseItem(detail.id, displayId);
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error(t("removeFailed"), errorCause(e)?.message);
    }
  };

  const publish = async () => {
    if (!detail) return;
    setConfirmPublish(false);
    setBusy(true);
    try {
      await publishRelease(detail.id);
      await Promise.all([refreshDetail(), reload()]);
      notify.success(t("status.RELEASED"));
    } catch (e) {
      notify.error(t("publishFailed"), errorCause(e)?.message);
    } finally {
      setBusy(false);
    }
  };

  const cancelRelease = async () => {
    if (!detail) return;
    setConfirmCancel(false);
    setBusy(true);
    try {
      await cancelReleaseRequest(detail.id);
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error(t("cancelFailed"), errorCause(e)?.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page testId="page-releases">
      <PageHeader
        title={t("title", { key: projectKey })}
        testId="releases-header"
        actions={
          <Button
            appearance="primary"
            testId="release-create-button"
            onClick={() => setShowCreate(true)}
          >
            {t("create")}
          </Button>
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={reload} testId="releases-error" />
      ) : loading ? (
        <Box xcss={styles.loading} style={centeredRow} testId="releases-loading">
          <Spinner size="large" />
        </Box>
      ) : (releases ?? []).length === 0 ? (
        <Box testId="releases-empty">
          <EmptyState header={t("empty")} description={t("emptyDescription")} />
        </Box>
      ) : (
        <table className="rdm-table" aria-label={t("tableLabel")} data-testid="release-table">
          <thead>
            <tr>
              <th scope="col">{t("col.name")}</th>
              <th scope="col" className="col-status">
                {t("col.status")}
              </th>
              <th scope="col" className="col-start">
                {t("col.target")}
              </th>
              <th scope="col" className="col-progress">
                {t("col.progress")}
              </th>
              <th scope="col" className="col-end">
                {t("col.released")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(releases ?? []).map((release) => (
              <tr
                key={release.id}
                data-clickable="true"
                tabIndex={0}
                data-testid={`release-row-${release.id}`}
                onClick={() => void openDetail(release.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    void openDetail(release.id);
                  }
                }}
              >
                <td>
                  <Text color="color.link">{release.name}</Text>
                </td>
                <td>
                  <span onClick={(e) => e.stopPropagation()}>
                    <ReleaseStatusLozenge status={release.status} />
                  </span>
                </td>
                <td>
                  <span className="cell-meta">{release.target_date ?? "—"}</span>
                </td>
                <td>
                  <ReleaseProgress
                    stats={release.stats}
                    label={`${release.name} ${t("col.progress")}`}
                  />
                </td>
                <td>
                  <span className="cell-meta">
                    {release.released_at ? formatDate(release.released_at) : "—"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <ReleaseFormDialog
        open={showCreate}
        title={t("form.createTitle")}
        projectKey={projectKey}
        onClose={() => setShowCreate(false)}
        onSave={create}
      />
      <ReleaseFormDialog
        open={showEdit}
        title={t("form.editTitle")}
        projectKey={projectKey}
        initial={
          detail
            ? {
                name: detail.name,
                description_md: detail.description_md ?? "",
                target_date: detail.target_date,
              }
            : undefined
        }
        onClose={() => setShowEdit(false)}
        onSave={saveEdit}
      />

      <Drawer
        isOpen={detailId !== null}
        onClose={() => {
          setDetailId(null);
          setDetail(null);
        }}
        width="wide"
        label={t("drawerLabel")}
        isFocusLockEnabled={!isBackdrop}
        autoFocusFirstElem={!isBackdrop}
        testId="release-detail-drawer"
      >
        {detail && (
          <div className="rdm-drawer-shell">
            <div className="rdm-drawer-header" data-testid="release-detail-header">
              <Box xcss={styles.detail} testId="release-detail">
                <Stack space="space.200">
                  <Inline space="space.150" alignBlock="center" shouldWrap>
                    <ReleaseStatusLozenge status={detail.status} />
                    <Heading size="medium">{detail.name}</Heading>
                    {detail.status === "PLANNED" && (
                      <Button
                        spacing="compact"
                        testId="release-detail-edit"
                        onClick={() => setShowEdit(true)}
                      >
                        {t("edit")}
                      </Button>
                    )}
                  </Inline>
                  {detail.target_date && (
                    <Text size="small" color="color.text.subtlest">
                      {t("col.target")}: {detail.target_date}
                    </Text>
                  )}
                  {detail.released_at && (
                    <Text size="small" color="color.text.subtlest">
                      {t("col.released")}: {formatDate(detail.released_at)}
                    </Text>
                  )}
                  {detail.description_md && (
                    <MarkdownText source={detail.description_md} onImageClick={setPreview} />
                  )}
                  <ReleaseProgress
                    stats={detail.stats}
                    label={`${detail.name} ${t("col.progress")}`}
                  />
                  <Inline space="space.075" shouldWrap>
                    {Object.entries(detail.status_counts).map(([status, count]) => (
                      <StatusLozenge key={status} status={status}>
                        {`${status}: ${count}`}
                      </StatusLozenge>
                    ))}
                  </Inline>

                  <Heading size="small">{t("readinessHeading")}</Heading>
                  {detail.stats.total === 0 ? (
                    <Text size="small" color="color.text.subtlest">
                      {t("emptyScope")}
                    </Text>
                  ) : detail.readiness.blocking.length === 0 ? (
                    <Text size="small" color="color.text.success">
                      {t("ready")}
                    </Text>
                  ) : (
                    <Stack space="space.050">
                      <Text size="small" color="color.text.warning">
                        {t("blockingSummary", { count: detail.readiness.blocking.length })}
                      </Text>
                      <Text size="small" color="color.text.subtlest">
                        {detail.readiness.blocking
                          .map((item) => `${item.display_id} (${item.status})`)
                          .join(", ")}
                      </Text>
                    </Stack>
                  )}
                </Stack>
              </Box>
            </div>

            <div className="rdm-drawer-list" data-testid="release-detail-list">
              <Box xcss={styles.listHeading}>
                <Heading size="small">{t("itemsHeading")}</Heading>
              </Box>
              {detail.items.length === 0 ? (
                <Box xcss={styles.emptyList}>
                  <Text size="small" color="color.text.subtlest">
                    {t("noItems")}
                  </Text>
                </Box>
              ) : (
                <div
                  className="rdm-scroll-area"
                  data-testid="release-detail-items-scroll"
                >
                  <table
                    className="rdm-table rdm-table--contained"
                    aria-label={t("itemsTableLabel")}
                    data-testid="release-detail-items"
                  >
                    <thead>
                      <tr>
                        <th scope="col" className="col-id">
                          ID
                        </th>
                        <th scope="col">{t("col.title")}</th>
                        <th scope="col" className="col-status">
                          {t("col.status")}
                        </th>
                        <th scope="col" className="col-count">
                          {t("col.actions")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.items.map((row) => (
                        <tr key={row.id} data-testid={`release-item-row-${row.display_id}`}>
                          <td>
                            <Inline space="space.075" alignBlock="center">
                              <TypeKindIcon kind={row.kind} />
                              <TextButton
                                data-testid={`release-item-open-${row.display_id}`}
                                onClick={() => {
                                  // The release drawer stays mounted behind the
                                  // item drawer.
                                  suppressDrawerEnter("release");
                                  openWorkItem(projectKey, row.display_id);
                                }}
                              >
                                {row.display_id}
                              </TextButton>
                            </Inline>
                          </td>
                          <td>
                            <TruncatedText className="title-text" text={row.title} />
                          </td>
                          <td>
                            <StatusLozenge status={row.status} />
                          </td>
                          <td>
                            {detail.status === "PLANNED" && (
                              <TextButton
                                danger
                                data-testid={`release-item-remove-${row.display_id}`}
                                onClick={() => void removeItem(row.display_id)}
                              >
                                {t("remove")}
                              </TextButton>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {detail.status === "PLANNED" && (
              <div className="rdm-drawer-footer" data-testid="release-detail-footer">
                <Stack space="space.150">
                  <Inline space="space.100" alignBlock="center">
                    <Button testId="release-item-add" onClick={() => setPickerOpen(true)}>
                      {t("add")}
                    </Button>
                  </Inline>
                  <Inline space="space.100">
                    <Button
                      appearance="primary"
                      isDisabled={!detail.readiness.can_publish}
                      testId="release-publish"
                      onClick={() => setConfirmPublish(true)}
                    >
                      {t("publish")}
                    </Button>
                    <Button
                      appearance="warning"
                      testId="release-cancel"
                      onClick={() => setConfirmCancel(true)}
                    >
                      {t("cancel")}
                    </Button>
                  </Inline>
                </Stack>
              </div>
            )}
          </div>
        )}
      </Drawer>

      <ConfirmDialog
        open={confirmPublish}
        title={t("publishConfirm.title")}
        confirmLabel={t("publishConfirm.confirmLabel")}
        busy={busy}
        testId="release-publish-dialog"
        onClose={() => setConfirmPublish(false)}
        onConfirm={() => void publish()}
      >
        {t("publishConfirm.body")}
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmCancel}
        title={t("cancelConfirm.title")}
        confirmLabel={t("cancelConfirm.confirmLabel")}
        danger
        busy={busy}
        testId="release-cancel-dialog"
        onClose={() => setConfirmCancel(false)}
        onConfirm={() => void cancelRelease()}
      >
        {t("cancelConfirm.body")}
      </ConfirmDialog>
      <ImagePreviewDialog
        open={preview !== null}
        src={preview?.src ?? null}
        alt={preview?.alt}
        onClose={() => setPreview(null)}
      />
      <WorkItemPickerDialog
        open={pickerOpen}
        projectKey={projectKey}
        allowedKinds={["story", "issue"]}
        excludeIds={detail?.items.map((item) => item.id) ?? []}
        excludeStatuses={["PUBLISHED", "CANCELLED", "CLOSED_REJECTED"]}
        confirmLabel={t("add")}
        onClose={() => setPickerOpen(false)}
        onConfirm={(items) => void addItems(items)}
      />
    </Page>
  );
}
