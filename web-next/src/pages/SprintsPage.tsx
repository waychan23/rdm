import { useCallback, useState } from "react";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Button from "@atlaskit/button/default/button";
import Drawer from "@atlaskit/drawer";
import EmptyState from "@atlaskit/empty-state";
import Heading from "@atlaskit/heading";
import Spinner from "@atlaskit/spinner";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import ConfirmDialog from "../components/ConfirmDialog";
import ErrorState from "../components/ErrorState";
import ImagePreviewDialog from "../components/ImagePreviewDialog";
import MarkdownText from "../components/MarkdownText";
import { Page, PageHeader } from "../components/Page";
import TextButton from "../components/TextButton";
import WorkItemPicker, { type WorkItemOption } from "../components/WorkItemPicker";
import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import type { Sprint, SprintDetail } from "../types";
import StatusLozenge from "../workitems/status";
import SprintFormDialog, { type SprintFormValues } from "./sprints/SprintFormDialog";
import "../styles/table.css";

function sprintLozenge(status: string) {
  if (status === "ACTIVE") return <StatusLozenge status="IN_PROGRESS" />;
  if (status === "CLOSED") return <StatusLozenge status="DONE" />;
  return <StatusLozenge status="TODO" />;
}

const centeredRow = { display: "flex", justifyContent: "center" } as const;

export default function SprintsPage() {
  const { t } = useTranslation("sprints");
  const { key: projectKey = "" } = useParams();
  const notify = useNotify();
  const [showCreate, setShowCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SprintDetail | null>(null);
  const [itemRefs, setItemRefs] = useState<WorkItemOption[]>([]);
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadSprints = useCallback(
    async () => (await api.get<Sprint[]>(`/projects/${projectKey}/sprints`)).data,
    [projectKey],
  );
  const { data: sprints, loading, error, reload } = useAsync(loadSprints, [projectKey]);

  const openDetail = useCallback(
    async (id: string) => {
      setDetailId(id);
      try {
        const res = await api.get<SprintDetail>(`/sprints/${id}`);
        setDetail(res.data);
      } catch (e) {
        notify.error(t("loadFailed"), errorCause(e)?.message);
      }
    },
    [notify, t],
  );

  const refreshDetail = useCallback(async () => {
    if (detailId) {
      const res = await api.get<SprintDetail>(`/sprints/${detailId}`);
      setDetail(res.data);
    }
  }, [detailId]);

  const create = async (v: SprintFormValues) => {
    try {
      await api.post(`/projects/${projectKey}/sprints`, v);
      setShowCreate(false);
      await reload();
    } catch (e) {
      notify.error(t("createFailed"), errorCause(e)?.message);
    }
  };

  const saveEdit = async (v: SprintFormValues) => {
    if (!detail) return;
    try {
      await api.patch(`/sprints/${detail.id}`, v);
      setShowEdit(false);
      await Promise.all([refreshDetail(), reload()]);
      notify.success(t("saveSuccess"));
    } catch (e) {
      notify.error(t("saveFailed"), errorCause(e)?.message);
    }
  };

  const addItem = async () => {
    if (!detail || itemRefs.length === 0 || busy) return;
    setBusy(true);
    try {
      await api.post(`/sprints/${detail.id}/items`, {
        items: itemRefs.map((item) => item.display_id),
      });
      setItemRefs([]);
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
      await api.del(`/sprints/${detail.id}/items/${encodeURIComponent(displayId)}`);
      await refreshDetail();
    } catch (e) {
      notify.error(t("removeFailed"), errorCause(e)?.message);
    }
  };

  const startSprint = async () => {
    if (!detail) return;
    try {
      await api.post(`/sprints/${detail.id}/start`, {});
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error(t("startFailed"), errorCause(e)?.message);
    }
  };

  const doClose = async () => {
    if (!detail) return;
    setConfirmClose(false);
    try {
      await api.post(`/sprints/${detail.id}/close`, {});
      await Promise.all([refreshDetail(), reload()]);
    } catch (e) {
      notify.error(t("closeFailed"), errorCause(e)?.message);
    }
  };

  return (
    <Page testId="page-sprints">
      <PageHeader
        title={t("title", { key: projectKey })}
        testId="sprints-header"
        actions={
          <Button
            appearance="primary"
            testId="sprint-create-button"
            onClick={() => setShowCreate(true)}
          >
            {t("create")}
          </Button>
        }
      />

      {error ? (
        <ErrorState error={error} onRetry={reload} testId="sprints-error" />
      ) : loading ? (
        <Box padding="space.400" style={centeredRow} testId="sprints-loading">
          <Spinner size="large" />
        </Box>
      ) : (sprints ?? []).length === 0 ? (
        <Box testId="sprints-empty">
          <EmptyState
            header={t("empty")}
            description={t("emptyDescription")}
          />
        </Box>
      ) : (
        <table
          className="rdm-table"
          aria-label={t("tableLabel")}
          data-testid="sprint-table"
        >
          <thead>
            <tr>
              <th scope="col">{t("col.name")}</th>
              <th scope="col" className="col-status">
                {t("col.status")}
              </th>
              <th scope="col" className="col-start">
                {t("col.start")}
              </th>
              <th scope="col" className="col-end">
                {t("col.end")}
              </th>
            </tr>
          </thead>
          <tbody>
            {(sprints ?? []).map((s) => (
              <tr
                key={s.id}
                data-clickable="true"
                tabIndex={0}
                data-testid={`sprint-row-${s.id}`}
                onClick={() => void openDetail(s.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    void openDetail(s.id);
                  }
                }}
              >
                <td>
                  <Text color="color.link">{s.name}</Text>
                </td>
                <td>
                  <span onClick={(e) => e.stopPropagation()}>{sprintLozenge(s.status)}</span>
                </td>
                <td>
                  <span className="cell-meta">{s.start_date ?? "—"}</span>
                </td>
                <td>
                  <span className="cell-meta">{s.end_date ?? "—"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <SprintFormDialog
        open={showCreate}
        title={t("form.createTitle")}
        projectKey={projectKey}
        onClose={() => setShowCreate(false)}
        onSave={create}
      />
      <SprintFormDialog
        open={showEdit}
        title={t("form.editTitle")}
        projectKey={projectKey}
        initial={
          detail
            ? {
                name: detail.name,
                goal_md: detail.goal_md ?? "",
                start_date: detail.start_date,
                end_date: detail.end_date,
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
        testId="sprint-detail-drawer"
      >
        {detail && (
          <Box padding="space.300" testId="sprint-detail">
            <Stack space="space.200">
              <Inline space="space.150" alignBlock="center">
                {sprintLozenge(detail.status)}
                <Heading size="medium">{detail.name}</Heading>
                {detail.status !== "CLOSED" && (
                  <Button
                    spacing="compact"
                    testId="sprint-detail-edit"
                    onClick={() => setShowEdit(true)}
                  >
                    {t("edit")}
                  </Button>
                )}
              </Inline>
              {detail.goal_md && (
                <MarkdownText source={detail.goal_md} onImageClick={setPreview} />
              )}
              <Inline space="space.075" shouldWrap>
                {Object.entries(detail.status_counts).map(([s, n]) => (
                  <StatusLozenge key={s} status={s}>
                    {`${s}: ${n}`}
                  </StatusLozenge>
                ))}
              </Inline>

              <Heading size="small">{t("itemsHeading")}</Heading>
              {detail.items.length === 0 ? (
                <Text size="small" color="color.text.subtlest">
                  {t("noItems")}
                </Text>
              ) : (
                <table
                  className="rdm-table"
                  aria-label={t("itemsTableLabel")}
                  data-testid="sprint-detail-items"
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
                      <tr key={row.id} data-testid={`sprint-item-row-${row.display_id}`}>
                        <td>
                          <Text color="color.link">{row.display_id}</Text>
                        </td>
                        <td>{row.title}</td>
                        <td>
                          <StatusLozenge status={row.status} />
                        </td>
                        <td>
                          {detail.status !== "CLOSED" && (
                            <TextButton
                              danger
                              data-testid={`sprint-item-remove-${row.display_id}`}
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

              {detail.status !== "CLOSED" && (
                <Stack space="space.150">
                  <Inline space="space.100" alignBlock="end">
                    <div style={{ flex: 1 }}>
                      <WorkItemPicker
                        isMulti
                        projectKey={projectKey}
                        allowedKinds={["story", "issue", "task"]}
                        excludeIds={detail.items.map((item) => item.id)}
                        backlogOnly
                        value={itemRefs}
                        onChange={setItemRefs}
                        placeholder={t("pickerPlaceholder")}
                        testId="sprint-item-input"
                      />
                    </div>
                    <Button
                      isLoading={busy}
                      isDisabled={itemRefs.length === 0}
                      testId="sprint-item-add"
                      onClick={() => void addItem()}
                    >
                      {t("add")}
                    </Button>
                  </Inline>
                  <Inline space="space.100">
                    {detail.status === "PLANNED" && (
                      <Button
                        appearance="primary"
                        testId="sprint-start"
                        onClick={() => void startSprint()}
                      >
                        {t("start")}
                      </Button>
                    )}
                    {detail.status === "ACTIVE" && (
                      <Button
                        appearance="warning"
                        testId="sprint-close"
                        onClick={() => setConfirmClose(true)}
                      >
                        {t("close")}
                      </Button>
                    )}
                  </Inline>
                </Stack>
              )}
            </Stack>
          </Box>
        )}
      </Drawer>

      <ConfirmDialog
        open={confirmClose}
        title={t("closeConfirm.title")}
        confirmLabel={t("closeConfirm.confirmLabel")}
        testId="sprint-close-dialog"
        onClose={() => setConfirmClose(false)}
        onConfirm={() => void doClose()}
      >
        {t("closeConfirm.body")}
      </ConfirmDialog>
      <ImagePreviewDialog
        open={preview !== null}
        src={preview?.src ?? null}
        alt={preview?.alt}
        onClose={() => setPreview(null)}
      />
    </Page>
  );
}
