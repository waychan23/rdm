import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import Button from "@atlaskit/button/default/button";
import Drawer from "@atlaskit/drawer";
import Heading from "@atlaskit/heading";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import ConfirmDialog from "../../components/ConfirmDialog";
import ImagePreviewDialog from "../../components/ImagePreviewDialog";
import MarkdownText from "../../components/MarkdownText";
import TextButton from "../../components/TextButton";
import WorkItemPickerDialog from "../../components/WorkItemPickerDialog";
import { api, errorCause } from "../../lib/api";
import { useNotify } from "../../lib/flags";
import type { SprintDetail, WorkItem } from "../../types";
import StatusLozenge from "../../workitems/status";
import SprintFormDialog, { type SprintFormValues } from "./SprintFormDialog";
import { sprintLozenge } from "./sprintStatus";

interface Props {
  projectKey: string;
  /** Null keeps the drawer closed; changing it loads that sprint. */
  sprintId: string | null;
  onClose: () => void;
  /** Host pages refresh their sprint list / board after a mutation. */
  onChanged?: () => void;
}

/** Sprint overview drawer shared by the sprint page and the board filters. */
export default function SprintDetailDrawer({
  projectKey,
  sprintId,
  onClose,
  onChanged,
}: Props) {
  const { t } = useTranslation("sprints");
  const notify = useNotify();
  const [detail, setDetail] = useState<SprintDetail | null>(null);
  const [showEdit, setShowEdit] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [busy, setBusy] = useState(false);

  const refreshDetail = useCallback(async () => {
    if (!sprintId) return;
    try {
      const res = await api.get<SprintDetail>(`/sprints/${sprintId}`);
      setDetail(res.data);
    } catch (e) {
      notify.error(t("loadFailed"), errorCause(e)?.message);
    }
  }, [sprintId, notify, t]);

  useEffect(() => {
    setDetail(null);
    setShowEdit(false);
    setPickerOpen(false);
    setConfirmClose(false);
    if (sprintId) void refreshDetail();
  }, [sprintId, refreshDetail]);

  const afterMutation = async () => {
    await refreshDetail();
    onChanged?.();
  };

  const saveEdit = async (v: SprintFormValues) => {
    if (!detail) return;
    try {
      await api.patch(`/sprints/${detail.id}`, v);
      setShowEdit(false);
      await afterMutation();
      notify.success(t("saveSuccess"));
    } catch (e) {
      notify.error(t("saveFailed"), errorCause(e)?.message);
    }
  };

  const addItems = async (items: WorkItem[]) => {
    if (!detail || items.length === 0 || busy) return;
    setBusy(true);
    try {
      await api.post(`/sprints/${detail.id}/items`, {
        items: items.map((item) => item.display_id),
      });
      setPickerOpen(false);
      await afterMutation();
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
      await afterMutation();
    } catch (e) {
      notify.error(t("removeFailed"), errorCause(e)?.message);
    }
  };

  const startSprint = async () => {
    if (!detail) return;
    try {
      await api.post(`/sprints/${detail.id}/start`, {});
      await afterMutation();
    } catch (e) {
      notify.error(t("startFailed"), errorCause(e)?.message);
    }
  };

  const doClose = async () => {
    if (!detail) return;
    setConfirmClose(false);
    try {
      await api.post(`/sprints/${detail.id}/close`, {});
      await afterMutation();
    } catch (e) {
      notify.error(t("closeFailed"), errorCause(e)?.message);
    }
  };

  return (
    <>
      <Drawer
        isOpen={sprintId !== null}
        onClose={onClose}
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
                  className="rdm-table rdm-table--contained"
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
                  <Inline space="space.100" alignBlock="center">
                    <Button
                      testId="sprint-item-add"
                      onClick={() => setPickerOpen(true)}
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

      <WorkItemPickerDialog
        open={pickerOpen}
        projectKey={projectKey}
        allowedKinds={["story", "issue", "task"]}
        excludeIds={detail?.items.map((item) => item.id) ?? []}
        confirmLabel={t("add")}
        onClose={() => setPickerOpen(false)}
        onConfirm={(items) => void addItems(items)}
      />

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
    </>
  );
}
