import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import Checkbox from "@atlaskit/checkbox";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import { api } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { statusLabel } from "../lib/labels";
import { itemPath } from "../lib/navigation";
import { useOpenOrigin } from "../lib/originSearch";
import { userLabel } from "../lib/users";
import type { Assignee, Sprint, WorkflowDto } from "../types";
import { kindOptions } from "./constants";
import { sprintLozenge } from "../pages/sprints/sprintStatus";
import SprintDetailDrawer from "../pages/sprints/SprintDetailDrawer";
import TextButton from "../components/TextButton";
import type {
  HasChildrenFilter,
  WorkItemFilters,
  WorkItemOrder,
} from "./filterState";
import { buildRequestParams } from "./filterState";

export type WorkItemView = "flat" | "tree";

interface Option {
  label: string;
  value: string;
}

interface SprintOption extends Option {
  sprint: Sprint;
}

interface FilterOptions {
  statuses: string[];
  assignees: Assignee[];
  participants: Assignee[];
}

interface Props {
  projectKey: string;
  filters: WorkItemFilters;
  /** Workflow drives the subtype options and the status option order. */
  workflow?: WorkflowDto | null;
  onFilterChange: (patch: Partial<WorkItemFilters>) => void;
  /** `/issues` pins the kind and hides the type filter. */
  kindFixed?: boolean;
  /** List page only: flat/tree view selector. */
  view?: WorkItemView;
  onViewChange?: (view: WorkItemView) => void;
  onCreate?: () => void;
  onRefresh?: () => void;
  showCreate?: boolean;
  showRefresh?: boolean;
}

const styles = cssMap({
  sprint: { width: "230px" },
  kind: { width: "300px" },
  subtype: { width: "180px" },
  hasChildren: { width: "150px" },
  completed: { width: "150px" },
  status: { width: "200px" },
  person: { width: "200px" },
  search: { width: "260px" },
  order: { width: "200px" },
  view: { width: "120px" },
});

function sprintDates(sprint: Sprint): string {
  return `${sprint.start_date ?? "—"} ~ ${sprint.end_date ?? "—"}`;
}

/** Workflow state order, used to keep status options in a stable, familiar order. */
function workflowStates(workflow: WorkflowDto | null | undefined): string[] {
  const out: string[] = [];
  const push = (value: string) => {
    if (!out.includes(value)) out.push(value);
  };
  Object.values(workflow?.kinds ?? {}).forEach((kind) => {
    kind.states.forEach(push);
    Object.values(kind.subtypes ?? {}).forEach((subtype) =>
      subtype.states.forEach(push),
    );
  });
  return out;
}

/**
 * Filter / sort / view controls shared by the work item list and the board
 * (RDM-63). Pages own the URL state; this component renders controls and
 * fetches the iteration list plus the pre-filtered facet options.
 */
export default function WorkItemToolbar({
  projectKey,
  filters,
  workflow,
  onFilterChange,
  kindFixed = false,
  view,
  onViewChange,
  onCreate,
  onRefresh,
  showCreate = true,
  showRefresh = true,
}: Props) {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const openOrigin = useOpenOrigin();
  const [qInput, setQInput] = useState(filters.q);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [sprintDrawerOpen, setSprintDrawerOpen] = useState(false);
  const [sprintsNonce, setSprintsNonce] = useState(0);

  useEffect(() => setQInput(filters.q), [filters.q]);

  useEffect(() => {
    let alive = true;
    api
      .get<Sprint[]>(`/projects/${projectKey}/sprints`)
      .then((res) => {
        if (alive) setSprints(res.data);
      })
      .catch(() => {
        // The filter stays empty; the data view still works unfiltered.
      });
    return () => {
      alive = false;
    };
  }, [projectKey, sprintsNonce]);

  // Status / assignee / participant options are computed over the
  // unpaginated filtered set; each dimension excludes its own selection
  // server-side so a multi-select keeps every option visible.
  const requestParams = buildRequestParams(filters).toString();
  const optionsState = useAsync<FilterOptions>(
    async () => {
      const res = await api.get<FilterOptions>(
        `/projects/${projectKey}/work-items/filter-options?${requestParams}`,
      );
      return res.data;
    },
    [projectKey, requestParams],
  );
  const facets = optionsState.data;

  const sprintOptions: SprintOption[] = useMemo(
    () =>
      sprints.map((sprint) => ({
        label: sprint.name,
        value: sprint.id,
        sprint,
      })),
    [sprints],
  );
  const activeSprint = useMemo(
    () => sprints.find((sprint) => sprint.id === filters.sprint) ?? null,
    [sprints, filters.sprint],
  );

  const statusOptions = useMemo<Option[]>(() => {
    const order = workflowStates(workflow);
    const values = [...(facets?.statuses ?? [])];
    values.sort((a, b) => {
      const ai = order.indexOf(a);
      const bi = order.indexOf(b);
      if (ai === -1 && bi === -1) return a.localeCompare(b);
      if (ai === -1) return 1;
      if (bi === -1) return -1;
      return ai - bi;
    });
    return values.map((value) => ({ label: statusLabel(value), value }));
  }, [facets?.statuses, workflow]);

  const subtypeOptions = useMemo<Option[]>(
    () => (workflow?.task_types ?? []).map(({ value, label }) => ({ label, value })),
    [workflow?.task_types],
  );

  const kindSelectOptions = useMemo(() => kindOptions(), []);
  const hasChildrenOptions: Option[] = useMemo(
    () => [
      { label: t("workItemFilters.hasChildrenYes"), value: "true" },
      { label: t("workItemFilters.hasChildrenNo"), value: "false" },
    ],
    [t],
  );
  const completedOptions: Option[] = useMemo(
    () => [
      { label: t("workItemFilters.completedYes"), value: "true" },
      { label: t("workItemFilters.completedNo"), value: "false" },
    ],
    [t],
  );
  const orderOptions: Option[] = useMemo(
    () => [
      { label: t("workItemFilters.orderComposite"), value: "composite" },
      { label: t("workItemFilters.orderCreatedDesc"), value: "created_desc" },
      { label: t("workItemFilters.orderCreatedAsc"), value: "created_asc" },
    ],
    [t],
  );
  const viewOptions: Option[] = useMemo(
    () => [
      { label: t("backlog.view.tree"), value: "tree" },
      { label: t("backlog.view.flat"), value: "flat" },
    ],
    [t],
  );

  const personOptions = (users: Assignee[] | undefined): Option[] =>
    (users ?? []).map((user) => ({ label: userLabel(user), value: user.id }));

  // An empty kind selection means "all types", which includes tasks.
  const showSubtype =
    !kindFixed && (filters.kinds.length === 0 || filters.kinds.includes("task"));

  return (
    <Stack space="space.100">
      {/* Row 1: search, high-frequency locators and page actions (RDM-108). */}
      <Inline
        space="space.100"
        alignBlock="center"
        spread="space-between"
        shouldWrap
        testId="work-item-filters"
      >
        <Inline space="space.100" alignBlock="center" shouldWrap>
          <Box xcss={styles.search}>
            <Textfield
              placeholder={t("workItemFilters.search")}
              value={qInput}
              testId="work-item-search"
              onChange={(event) => setQInput(event.currentTarget.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") onFilterChange({ q: qInput.trim() });
              }}
              onBlur={() => {
                if (filters.q !== qInput.trim()) onFilterChange({ q: qInput.trim() });
              }}
            />
          </Box>

          <Box xcss={styles.sprint} testId="work-item-filter-sprint">
            <Select<SprintOption>
              options={sprintOptions}
              value={sprintOptions.find((option) => option.value === filters.sprint) ?? null}
              onChange={(option) =>
                onFilterChange({ sprint: (option as SprintOption | null)?.value ?? "" })
              }
              isClearable
              spacing="compact"
              placeholder={t("workItemFilters.sprintPlaceholder")}
              formatOptionLabel={(option, meta) =>
                meta.context === "menu" ? (
                  <Inline space="space.100" alignBlock="center">
                    <Text size="small">{option.sprint.name}</Text>
                    {sprintLozenge(option.sprint.status)}
                    <Text size="small" color="color.text.subtle">
                      {sprintDates(option.sprint)}
                    </Text>
                  </Inline>
                ) : (
                  <Text size="small">{option.sprint.name}</Text>
                )
              }
              testId="work-item-sprint-select"
            />
          </Box>

          {!kindFixed && (
            <Box xcss={styles.kind} testId="work-item-filter-kind">
              <Select<Option, true>
                isMulti
                hideSelectedOptions={false}
                options={kindSelectOptions}
                value={kindSelectOptions.filter((option) =>
                  filters.kinds.includes(option.value),
                )}
                onChange={(options) =>
                  onFilterChange({ kinds: options.map((option) => option.value) })
                }
                spacing="compact"
                placeholder={t("workItemFilters.kindPlaceholder")}
                testId="work-item-kind-select"
              />
            </Box>
          )}

          {view && onViewChange && (
            <Box xcss={styles.view} testId="work-item-filter-view">
              <Select<Option>
                options={viewOptions}
                value={viewOptions.find((option) => option.value === view) ?? null}
                onChange={(option) =>
                  onViewChange(((option as Option | null)?.value as WorkItemView) ?? "tree")
                }
                spacing="compact"
                isClearable={false}
                testId="work-item-view-select"
              />
            </Box>
          )}

          <Box xcss={styles.order} testId="work-item-filter-order">
            <Select<Option>
              options={orderOptions}
              value={orderOptions.find((option) => option.value === filters.order) ?? null}
              onChange={(option) =>
                onFilterChange({
                  order: ((option as Option | null)?.value ??
                    "composite") as WorkItemOrder,
                })
              }
              spacing="compact"
              isClearable={false}
              testId="work-item-order-select"
            />
          </Box>
        </Inline>

        <Inline space="space.100" alignBlock="center" testId="work-item-toolbar-actions">
          {showRefresh && onRefresh && (
            <Button
              appearance="subtle"
              spacing="compact"
              testId="work-item-refresh"
              onClick={onRefresh}
            >
              {t("workItemFilters.refresh")}
            </Button>
          )}

          {showCreate && onCreate && (
            <Button
              appearance="primary"
              testId="work-item-create-button"
              onClick={onCreate}
            >
              {t("workItemFilters.create")}
            </Button>
          )}
        </Inline>
      </Inline>

      {/* Row 2: deep filters, people and child-item rules (RDM-108). */}
      <Inline
        space="space.100"
        alignBlock="center"
        shouldWrap
        testId="work-item-filters-secondary"
      >
        <Box xcss={styles.status} testId="work-item-filter-status">
          <Select<Option, true>
            isMulti
            hideSelectedOptions={false}
            options={statusOptions}
            value={statusOptions.filter((option) =>
              filters.statuses.includes(option.value),
            )}
            onChange={(options) =>
              onFilterChange({ statuses: options.map((option) => option.value) })
            }
            spacing="compact"
            placeholder={t("workItemFilters.statusPlaceholder")}
            testId="work-item-status-select"
          />
        </Box>

        <Box xcss={styles.completed} testId="work-item-filter-completed">
          <Select<Option>
            options={completedOptions}
            value={completedOptions.find((option) => option.value === filters.completed) ?? null}
            onChange={(option) =>
              onFilterChange({
                completed: ((option as Option | null)?.value ?? "") as
                  | ""
                  | "true"
                  | "false",
              })
            }
            isClearable
            spacing="compact"
            placeholder={t("workItemFilters.completionPlaceholder")}
            testId="work-item-completed-select"
          />
        </Box>

        {showSubtype && (
          <Box xcss={styles.subtype} testId="work-item-filter-subtype">
            <Select<Option, true>
              isMulti
              hideSelectedOptions={false}
              options={subtypeOptions}
              value={subtypeOptions.filter((option) =>
                filters.subtypes.includes(option.value),
              )}
              onChange={(options) =>
                onFilterChange({ subtypes: options.map((option) => option.value) })
              }
              spacing="compact"
              placeholder={t("workItemFilters.subtypePlaceholder")}
              testId="work-item-subtype-select"
            />
          </Box>
        )}

        <Box xcss={styles.person} testId="work-item-filter-assignee">
          <Select<Option, true>
            isMulti
            isSearchable
            hideSelectedOptions={false}
            options={personOptions(facets?.assignees)}
            value={personOptions(facets?.assignees).filter((option) =>
              filters.assignees.includes(option.value),
            )}
            onChange={(options) =>
              onFilterChange({ assignees: options.map((option) => option.value) })
            }
            spacing="compact"
            placeholder={t("workItemFilters.assigneePlaceholder")}
            testId="work-item-assignee-select"
          />
        </Box>

        <Box xcss={styles.person} testId="work-item-filter-participant">
          <Select<Option, true>
            isMulti
            isSearchable
            hideSelectedOptions={false}
            options={personOptions(facets?.participants)}
            value={personOptions(facets?.participants).filter((option) =>
              filters.participants.includes(option.value),
            )}
            onChange={(options) =>
              onFilterChange({ participants: options.map((option) => option.value) })
            }
            spacing="compact"
            placeholder={t("workItemFilters.participantPlaceholder")}
            testId="work-item-participant-select"
          />
        </Box>

        <Box xcss={styles.hasChildren} testId="work-item-filter-has-children">
          <Select<Option>
            options={hasChildrenOptions}
            value={
              hasChildrenOptions.find(
                (option) => option.value === filters.hasChildren,
              ) ?? null
            }
            onChange={(option) =>
              onFilterChange({
                hasChildren: ((option as Option | null)?.value ??
                  "") as HasChildrenFilter,
              })
            }
            isClearable
            spacing="compact"
            placeholder={t("workItemFilters.hasChildrenPlaceholder")}
            testId="work-item-has-children-select"
          />
        </Box>

        <Checkbox
          label={t("workItemFilters.rootOnly")}
          isChecked={filters.rootOnly}
          testId="work-item-filter-root-only"
          onChange={(event) => onFilterChange({ rootOnly: event.currentTarget.checked })}
        />
      </Inline>

      {activeSprint && (
        <Inline space="space.150" alignBlock="center" testId="work-item-sprint-info">
          <TextButton
            data-testid="work-item-sprint-open"
            onClick={() => setSprintDrawerOpen(true)}
          >
            {activeSprint.name}
          </TextButton>
          <Text size="small" color="color.text.subtle">
            {t("board.sprintDates", {
              start: activeSprint.start_date ?? "—",
              end: activeSprint.end_date ?? "—",
            })}
          </Text>
          {sprintLozenge(activeSprint.status)}
        </Inline>
      )}

      <SprintDetailDrawer
        projectKey={projectKey}
        sprintId={sprintDrawerOpen ? filters.sprint || null : null}
        onClose={() => setSprintDrawerOpen(false)}
        onOpenItem={(item) =>
          navigate(itemPath(projectKey, item.display_id), { state: { from: openOrigin } })
        }
        onChanged={() => {
          setSprintsNonce((nonce) => nonce + 1);
          onRefresh?.();
        }}
      />
    </Stack>
  );
}
