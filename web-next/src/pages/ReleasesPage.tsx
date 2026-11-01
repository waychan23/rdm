import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
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
import WorkItemPickerDialog from "../components/WorkItemPickerDialog";
import { useAsync } from "../hooks/useAsync";
import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import { formatDate } from "../lib/format";
import type { Release, ReleaseDetail, ReleaseStats, WorkItem } from "../types";
import StatusLozenge from "../workitems/status";
import ReleaseFormDialog, { type ReleaseFormValues } from "./releases/ReleaseFormDialog";
import "../styles/table.css";

const centeredRow = { display: "flex", justifyContent: "center" } as const;

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
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReleaseDetail | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);
  const [confirmPublish, setConfirmPublish] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadReleases = useCallback(
    async () => (await api.get<Release[]>(`/projects/${projectKey}/releases`)).data,
    [projectKey],
  );
  const { data: releases, loading, error, reload } = useAsync(loadReleases, [projectKey]);

  const openDetail = useCallback(
    async (id: string) => {
      setDetailId(id);
      try {
        const res = await api.get<ReleaseDetail>(`/releases/${id}`);
        setDetail(res.data);
      } catch (e) {
        notify.error(t("loadFailed"), errorCause(e)?.message);
      }
    },
    [notify, t],
  );

  const refreshDetail = useCallback(async () => {
    if (detailId) {
      const res = await api.get<ReleaseDetail>(`/releases/${detailId}`);
      setDetail(res.data);
    }
  }, [detailId]);

  const create = async (values: ReleaseFormValues) => {
    try {
      await api.post(`/projects/${projectKey}/releases`, values);
      setShowCreate(false);
      await reload();
    } catch (e) {
      notify.error(t("createFailed"), errorCause(e)?.message);
    }
  };

  const saveEdit = async (values: ReleaseFormValues) => {
    if (!detail) return;
    try {
      await api.patch(`/releases/${detail.id}`, values);
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
      await api.post(`/releases/${detail.id}/items`, {
        items: items.map((item) => item.display_id),
      });
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
      await api.del(`/releases/${detail.id}/items/${encodeURIComponent(displayId)}`);
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
      await api.post(`/releases/${detail.id}/publish`, {});
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
      await api.post(`/releases/${detail.id}/cancel`, {});
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
        <Box padding="space.400" style={centeredRow} testId="releases-loading">
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
        testId="release-detail-drawer"
      >
        {detail && (
          <Box padding="space.300" testId="release-detail">
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

              <Heading size="small">{t("itemsHeading")}</Heading>
              {detail.items.length === 0 ? (
                <Text size="small" color="color.text.subtlest">
                  {t("noItems")}
                </Text>
              ) : (
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
                          <Text color="color.link">{row.display_id}</Text>
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
              )}

              {detail.status === "PLANNED" && (
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
              )}
            </Stack>
          </Box>
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
