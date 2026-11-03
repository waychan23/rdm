import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import Button from "@atlaskit/button/default/button";
import { cssMap } from "@atlaskit/css";
import Drawer from "@atlaskit/drawer";
import Heading from "@atlaskit/heading";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import ConfirmDialog from "../../components/ConfirmDialog";
import ImagePreviewDialog from "../../components/ImagePreviewDialog";
import MarkdownText from "../../components/MarkdownText";
import TextButton from "../../components/TextButton";
import TruncatedText from "../../components/TruncatedText";
import TypeKindIcon from "../../components/TypeKindIcon";
import WorkItemPickerDialog from "../../components/WorkItemPickerDialog";
import { api, errorCause } from "../../lib/api";
import { recallDetail, rememberDetail } from "../../lib/detailCache";
import { useNotify } from "../../lib/flags";
import { useListOrigin } from "../../lib/originSearch";
import type { SprintDetail, WorkItem } from "../../types";
import StatusLozenge from "../../workitems/status";
import SprintFormDialog, { type SprintFormValues } from "./SprintFormDialog";
import { sprintLozenge } from "./sprintStatus";

const styles = cssMap({
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

interface Props {
  projectKey: string;
  /** Null keeps the drawer closed; changing it loads that sprint. */
  sprintId: string | null;
  onClose: () => void;
  /** Open the work item drawer for a row in the sprint scope (RDM-102). */
  onOpenItem: (item: WorkItem) => void;
  /** Host pages refresh their sprint list / board after a mutation. */
  onChanged?: () => void;
}

/** Sprint overview drawer shared by the sprint page and the board filters. */
export default function SprintDetailDrawer({
  projectKey,
  sprintId,
  onClose,
  onOpenItem,
  onChanged,
}: Props) {
  const { t } = useTranslation("sprints");
  const notify = useNotify();
  // As a drawer backdrop, the work item drawer owns focus and Escape; the
  // sprint drawer only needs to stay visible underneath it.
  const isBackdrop = useListOrigin() !== null;
  const [detail, setDetail] = useState<SprintDetail | null>(() =>
    sprintId ? recallDetail<SprintDetail>(`sprint:${sprintId}`) : null,
  );
  const [showEdit, setShowEdit] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [preview, setPreview] = useState<{ src: string; alt: string } | null>(null);
  const [confirmClose, setConfirmClose] = useState(false);
  const [busy, setBusy] = useState(false);

  const refreshDetail = useCallback(async () => {
    if (!sprintId) return;
    try {
      const res = await api.get<SprintDetail>(`/sprints/${sprintId}`);
      rememberDetail(`sprint:${sprintId}`, res.data);
      setDetail(res.data);
    } catch (e) {
      notify.error(t("loadFailed"), errorCause(e)?.message);
    }
  }, [sprintId, notify, t]);

  useEffect(() => {
    // Re-mounts (item drawer backdrop / return to the page) start from the
    // cached payload so the drawer never renders empty for a frame.
    setDetail(sprintId ? recallDetail<SprintDetail>(`sprint:${sprintId}`) : null);
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
        isFocusLockEnabled={!isBackdrop}
        autoFocusFirstElem={!isBackdrop}
        testId="sprint-detail-drawer"
      >
        {detail && (
          <div className="rdm-drawer-shell">
            <div className="rdm-drawer-header" data-testid="sprint-detail-header">
              <Box xcss={styles.detail} testId="sprint-detail">
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
                </Stack>
              </Box>
            </div>

            <div className="rdm-drawer-list" data-testid="sprint-detail-list">
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
                  data-testid="sprint-detail-items-scroll"
                >
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
                            <Inline space="space.075" alignBlock="center">
                              <TypeKindIcon kind={row.kind} />
                              <TextButton
                                data-testid={`sprint-item-open-${row.display_id}`}
                                onClick={() => onOpenItem(row)}
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
                </div>
              )}
            </div>

            {detail.status !== "CLOSED" && (
              <div className="rdm-drawer-footer" data-testid="sprint-detail-footer">
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
              </div>
            )}
          </div>
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
