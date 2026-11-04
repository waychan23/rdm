import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Pagination from "@atlaskit/pagination";
import Select from "@atlaskit/select";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import { listWorkItems } from "../api/work-items-api";
import { getWorkflow } from "../api/workflow-api";
import { useAsync } from "../hooks/useAsync";
import { statusLabel } from "../lib/labels";
import { flattenMembers, loadProjectMembers } from "../lib/members";
import { portalMenuProps } from "../lib/portalMenu";
import { userLabel } from "../lib/users";
import type { Assignee, ProjectMemberRow, WorkItem, WorkflowDto } from "../types";
import { kindOptions } from "../workitems/constants";
import { buildRequestParams } from "../workitems/filterState";
import { priorityOptions } from "../workitems/priority";
import PriorityMark from "./PriorityMark";
import PersonCell from "./PersonCell";
import TruncatedText from "./TruncatedText";
import StatusLozenge from "../workitems/status";
import TypeKindIcon from "./TypeKindIcon";
import "../styles/table.css";

interface Option {
  label: string;
  value: string;
}

interface PickerFilters {
  kinds: string[];
  assignees: string[];
  priorities: string[];
  statuses: string[];
  q: string;
}

interface ItemsResult {
  items: WorkItem[];
  total: number;
}

interface Props {
  open: boolean;
  projectKey: string;
  /** Selectable kinds; the type filter can never leave this set. */
  allowedKinds: string[];
  /** Items already attached elsewhere are hidden from the result set. */
  excludeIds?: string[];
  excludeStatuses?: string[];
  title?: string;
  confirmLabel?: string;
  onClose: () => void;
  onConfirm: (items: WorkItem[]) => void;
}

const PAGE_SIZE = 20;

const styles = cssMap({
  content: {
    display: "flex",
    flexDirection: "column",
    gap: "var(--ds-space-150)",
    flex: "1",
    minHeight: "0",
    height: "100%",
  },
  filters: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "var(--ds-space-100)",
  },
  search: {
    gridColumn: "1 / -1",
  },
  tableWrap: {
    flex: "1",
    minHeight: "0",
    overflow: "auto",
  },
  empty: {
    paddingBlock: "var(--ds-space-400)",
    textAlign: "center",
  },
  center: {
    justifyContent: "center",
  },
});

const emptyFilters: PickerFilters = {
  kinds: [],
  assignees: [],
  priorities: [],
  statuses: [],
  q: "",
};

/**
 * Reusable work item picker dialog (RDM-39): search plus type/assignee/
 * priority/status filters over the same server-side list contract as the
 * backlog toolbar (RDM-63), with paged results and cross-page multi-select.
 */
export default function WorkItemPickerDialog({
  open,
  projectKey,
  allowedKinds,
  excludeIds = [],
  excludeStatuses = [],
  title,
  confirmLabel,
  onClose,
  onConfirm,
}: Props) {
  const { t } = useTranslation("components");
  const [filters, setFilters] = useState<PickerFilters>(emptyFilters);
  const [qInput, setQInput] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Map<string, WorkItem>>(new Map());

  const allowedKey = allowedKinds.join(",");
  const excludeKey = excludeIds.join(",");
  const excludedStatusKey = excludeStatuses.join(",");

  // Reset the dialog state each time it opens.
  useEffect(() => {
    if (!open) return;
    setFilters({ ...emptyFilters, kinds: [...allowedKinds] });
    setQInput("");
    setPage(1);
    setSelected(new Map());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectKey]);

  const membersState = useAsync<ProjectMemberRow[]>(
    async () => {
      if (!open) return [];
      return loadProjectMembers(projectKey);
    },
    [open, projectKey],
  );
  const workflowState = useAsync<WorkflowDto | null>(
    async () => {
      if (!open) return null;
      return getWorkflow(projectKey);
    },
    [open, projectKey],
  );
  const workflow = workflowState.data;

  const kindFilter = filters.kinds.length > 0 ? filters.kinds : allowedKinds;
  const requestParams = useMemo(() => {
    const params = buildRequestParams({
      sprint: "",
      kinds: kindFilter,
      subtypes: [],
      rootOnly: false,
      hasChildren: "",
      completed: "",
      statuses: filters.statuses,
      assignees: filters.assignees,
      participants: [],
      q: filters.q,
      order: "composite",
    });
    if (filters.priorities.length > 0) {
      params.set("priority", filters.priorities.join(","));
    }
    if (excludeIds.length > 0) params.set("exclude_ids", excludeIds.join(","));
    if (excludeStatuses.length > 0) {
      params.set("exclude_status", excludeStatuses.join(","));
    }
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String((page - 1) * PAGE_SIZE));
    return params.toString();
    // excludeKey/allowedKey stand in for the array identities.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    kindFilter.join(","),
    filters.statuses.join(","),
    filters.assignees.join(","),
    filters.priorities.join(","),
    filters.q,
    page,
    excludeKey,
    excludedStatusKey,
  ]);

  const itemsState = useAsync<ItemsResult>(
    async () => {
      if (!open) return { items: [], total: 0 };
      const res = await listWorkItems(projectKey, requestParams);
      return {
        items: res.data,
        total: Number(res.meta?.total ?? res.data.length),
      };
    },
    [open, projectKey, requestParams],
  );

  const rows = itemsState.data?.items ?? [];
  const total = itemsState.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const patch = (next: Partial<PickerFilters>) => {
    setFilters((current) => ({ ...current, ...next }));
    setPage(1);
  };

  const assigneeOptions = useMemo<Option[]>(
    () =>
      flattenMembers(membersState.data ?? []).map((user) => ({
        label: userLabel(user),
        value: user.id,
      })),
    [membersState.data],
  );

  const statusOptions = useMemo<Option[]>(() => {
    const states: string[] = [];
    const push = (value: string) => {
      if (!states.includes(value)) states.push(value);
    };
    kindFilter.forEach((kind) => {
      const spec = workflow?.kinds[kind];
      if (!spec) return;
      spec.states.forEach(push);
      Object.values(spec.subtypes ?? {}).forEach((subtype) =>
        subtype.states.forEach(push),
      );
    });
    return states.map((value) => ({ label: statusLabel(value), value }));
  }, [workflow, kindFilter.join(",")]);

  const kindSelectOptions = useMemo<Option[]>(() => {
    const allowed = new Set(allowedKinds);
    return kindOptions().filter((option) => allowed.has(option.value));
  }, [allowedKey]);

  const prioritySelectOptions = useMemo<Option[]>(
    () =>
      priorityOptions().map((option) => ({
        label: option.label,
        value: String(option.value),
      })),
    [],
  );

  const allPageSelected =
    rows.length > 0 && rows.every((item) => selected.has(item.id));

  const toggle = (item: WorkItem) => {
    setSelected((current) => {
      const next = new Map(current);
      if (next.has(item.id)) next.delete(item.id);
      else next.set(item.id, item);
      return next;
    });
  };

  const togglePage = () => {
    setSelected((current) => {
      const next = new Map(current);
      if (allPageSelected) {
        rows.forEach((item) => next.delete(item.id));
      } else {
        rows.forEach((item) => next.set(item.id, item));
      }
      return next;
    });
  };

  const confirm = () => onConfirm([...selected.values()]);

  return (
    <ModalTransition>
      {open && (
        <ModalDialog
          onClose={onClose}
          width="50vw"
          height="60vh"
          testId="work-item-picker-dialog"
        >
          <ModalHeader>
            <ModalTitle>{title ?? t("workItemPicker.title")}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Box xcss={styles.content}>
              <Box xcss={styles.filters}>
                <Box testId="work-item-picker-kind">
                  <Select<Option, true>
                    {...portalMenuProps}
                    isMulti
                    hideSelectedOptions={false}
                    options={kindSelectOptions}
                    value={kindSelectOptions.filter((option) =>
                      filters.kinds.includes(option.value),
                    )}
                    onChange={(options) =>
                      patch({ kinds: options.map((option) => option.value) })
                    }
                    spacing="compact"
                    placeholder={t("workItemPicker.allKinds")}
                    />
                </Box>
                <Box testId="work-item-picker-assignee">
                  <Select<Option, true>
                    {...portalMenuProps}
                    isMulti
                    isSearchable
                    hideSelectedOptions={false}
                    options={assigneeOptions}
                    value={assigneeOptions.filter((option) =>
                      filters.assignees.includes(option.value),
                    )}
                    onChange={(options) =>
                      patch({ assignees: options.map((option) => option.value) })
                    }
                    spacing="compact"
                    placeholder={t("workItemPicker.allAssignees")}
                    />
                </Box>
                <Box testId="work-item-picker-priority">
                  <Select<Option, true>
                    {...portalMenuProps}
                    isMulti
                    hideSelectedOptions={false}
                    options={prioritySelectOptions}
                    value={prioritySelectOptions.filter((option) =>
                      filters.priorities.includes(option.value),
                    )}
                    onChange={(options) =>
                      patch({ priorities: options.map((option) => option.value) })
                    }
                    spacing="compact"
                    placeholder={t("workItemPicker.allPriorities")}
                    />
                </Box>
                <Box testId="work-item-picker-status">
                  <Select<Option, true>
                    {...portalMenuProps}
                    isMulti
                    hideSelectedOptions={false}
                    options={statusOptions}
                    value={statusOptions.filter((option) =>
                      filters.statuses.includes(option.value),
                    )}
                    onChange={(options) =>
                      patch({ statuses: options.map((option) => option.value) })
                    }
                    spacing="compact"
                    placeholder={t("workItemPicker.allStatuses")}
                    />
                </Box>
                <Box xcss={styles.search}>
                  <Textfield
                    placeholder={t("workItemPicker.search")}
                    value={qInput}
                    testId="work-item-picker-search"
                    onChange={(event) => setQInput(event.currentTarget.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") patch({ q: qInput.trim() });
                    }}
                    onBlur={() => {
                      if (filters.q !== qInput.trim()) patch({ q: qInput.trim() });
                    }}
                  />
                </Box>
              </Box>

              <Inline space="space.150" alignBlock="center" spread="space-between">
                <Checkbox
                  label={t("workItemPicker.selectPage")}
                  isChecked={allPageSelected}
                  isDisabled={rows.length === 0}
                  testId="work-item-picker-select-page"
                  onChange={togglePage}
                />
                <Text size="small" color="color.text.subtlest">
                  {t("workItemPicker.total", { n: total })}
                </Text>
              </Inline>

              <Box xcss={styles.tableWrap}>
                {itemsState.loading && rows.length === 0 ? (
                  <Inline alignBlock="center" xcss={styles.center}>
                    <Spinner />
                  </Inline>
                ) : rows.length === 0 ? (
                  <Box xcss={styles.empty}>
                    <Text color="color.text.subtlest">{t("workItemPicker.empty")}</Text>
                  </Box>
                ) : (
                  <table
                    className="rdm-table rdm-table--contained"
                    aria-label={t("workItemPicker.title")}
                    data-testid="work-item-picker-table"
                  >
                    <thead>
                      <tr>
                        <th scope="col" className="col-checkbox" />
                        <th scope="col" className="col-id">
                          ID
                        </th>
                        <th scope="col">{t("workItemPicker.itemTitle")}</th>
                        <th scope="col">{t("workItemPicker.status")}</th>
                        <th scope="col">{t("workItemPicker.priority")}</th>
                        <th scope="col">{t("workItemPicker.assignee")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((item) => {
                        const checked = selected.has(item.id);
                        return (
                          <tr
                            key={item.id}
                            data-clickable="true"
                            data-testid={`work-item-picker-row-${item.display_id}`}
                            onClick={() => toggle(item)}
                          >
                            <td>
                              <Checkbox
                                label=""
                                isChecked={checked}
                                testId={`work-item-picker-check-${item.display_id}`}
                                onChange={(event) => {
                                  event.stopPropagation();
                                  toggle(item);
                                }}
                              />
                            </td>
                            <td>
                              <Inline space="space.050" alignBlock="center">
                                <TypeKindIcon kind={item.kind} />
                                <Text size="small" color="color.link">
                                  {item.display_id}
                                </Text>
                              </Inline>
                            </td>
                            <td>
                              <TruncatedText className="title-text" text={item.title} />
                            </td>
                            <td>
                              <StatusLozenge status={item.status} />
                            </td>
                            <td>
                              <PriorityMark priority={item.priority} />
                            </td>
                            <td>
                              <PersonCell
                                name={item.assignee ? userLabel(item.assignee) : undefined}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </Box>

              <Inline space="space.150" alignBlock="center" spread="space-between">
                <Text size="small" testId="work-item-picker-selected">
                  {t("workItemPicker.selected", { n: selected.size })}
                </Text>
                <Inline space="space.050">
                  {selected.size > 0 && (
                    <Button
                      appearance="subtle"
                      spacing="compact"
                      testId="work-item-picker-clear"
                      onClick={() => setSelected(new Map())}
                    >
                      {t("workItemPicker.clear")}
                    </Button>
                  )}
                  <Pagination
                    pages={Array.from({ length: pageCount }, (_, index) => index + 1)}
                    selectedIndex={Math.min(page, pageCount) - 1}
                    onChange={(_event, next) => setPage(Number(next))}
                  />
                </Inline>
              </Inline>
            </Box>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="work-item-picker-cancel">
              {t("workItemPicker.cancel")}
            </Button>
            <Button
              appearance="primary"
              isDisabled={selected.size === 0}
              onClick={confirm}
              testId="work-item-picker-confirm"
            >
              {confirmLabel ?? t("workItemPicker.confirm")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
