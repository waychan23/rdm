import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";
import Spinner from "@atlaskit/spinner";
import { Box, Text } from "@atlaskit/primitives/compiled";

import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import { api, errorCause } from "../lib/api";
import { useAsync } from "../hooks/useAsync";
import { useNotify } from "../lib/flags";
import { itemPath } from "../lib/navigation";
import {
  useListProjectKey,
  useListSearchParams,
  useOpenOrigin,
} from "../lib/originSearch";
import type { Sprint } from "../types";
import SprintDetailDrawer from "./sprints/SprintDetailDrawer";
import SprintFormDialog, { type SprintFormValues } from "./sprints/SprintFormDialog";
import { sprintLozenge } from "./sprints/sprintStatus";
import "../styles/table.css";

const centeredRow = { display: "flex", justifyContent: "center" } as const;

export default function SprintsPage() {
  const { t } = useTranslation("sprints");
  const { key: routeKey = "" } = useParams();
  // The origin URL owns the project while this page is a drawer backdrop.
  const projectKey = useListProjectKey(routeKey);
  const navigate = useNavigate();
  const openOrigin = useOpenOrigin();
  const notify = useNotify();
  const [searchParams, setSearchParams] = useListSearchParams();
  const [showCreate, setShowCreate] = useState(false);
  // URL-backed so the open detail drawer survives becoming the item drawer's
  // backdrop (opening a work item must not close the sprint drawer).
  const detailId = searchParams.get("sprint");
  const setDetailId = (id: string | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) next.set("sprint", id);
    else next.delete("sprint");
    setSearchParams(next, { replace: true });
  };

  const loadSprints = useCallback(
    async () => (await api.get<Sprint[]>(`/projects/${projectKey}/sprints`)).data,
    [projectKey],
  );
  const { data: sprints, loading, error, reload } = useAsync(loadSprints, [projectKey]);

  const create = async (v: SprintFormValues) => {
    try {
      await api.post(`/projects/${projectKey}/sprints`, v);
      setShowCreate(false);
      await reload();
    } catch (e) {
      notify.error(t("createFailed"), errorCause(e)?.message);
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
          <EmptyState header={t("empty")} description={t("emptyDescription")} />
        </Box>
      ) : (
        <table className="rdm-table" aria-label={t("tableLabel")} data-testid="sprint-table">
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
                onClick={() => setDetailId(s.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setDetailId(s.id);
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

      <SprintDetailDrawer
        projectKey={projectKey}
        sprintId={detailId}
        onClose={() => setDetailId(null)}
        onOpenItem={(item) =>
          navigate(itemPath(projectKey, item.display_id), { state: { from: openOrigin } })
        }
        onChanged={() => void reload()}
      />
    </Page>
  );
}
