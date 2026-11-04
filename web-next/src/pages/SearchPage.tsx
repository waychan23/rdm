import { useEffect, useState, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { cssMap } from "@atlaskit/css";
import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";
import Lozenge from "@atlaskit/lozenge";
import Spinner from "@atlaskit/spinner";
import Textfield from "@atlaskit/textfield";
import { Box, Inline, Stack, Text } from "@atlaskit/primitives/compiled";

import { cardBorder } from "../components/cardBorder";
import ErrorState from "../components/ErrorState";
import { Page, PageHeader } from "../components/Page";
import { useEventInstanceId } from "../hooks/useEventBus";
import { useWorkItemUpdatedRefresh } from "../hooks/useWorkItemEvents";
import { api } from "../lib/api";
import { searchTypeLabel } from "../lib/labels";
import { useOpenWorkItem } from "../lib/itemOverlay";
import { useItemOverlayOpen } from "../lib/itemOverlayVisibility";
import { useListSearchParams } from "../lib/originSearch";
import { useAsync } from "../hooks/useAsync";
import type { SearchHit } from "../types";

const styles = cssMap({
  card: {
    borderRadius: "var(--ds-radius-small)",
    paddingBlock: "var(--ds-space-150)",
    paddingInline: "var(--ds-space-200)",
    backgroundColor: "var(--ds-surface)",
    cursor: "pointer",
    "&:hover": { backgroundColor: "var(--ds-surface-hovered)" },
  },
  centered: {
    display: "flex",
    justifyContent: "center",
    padding: "var(--ds-space-400)",
  },
  snippet: {
    paddingBlockStart: "var(--ds-space-050)",
  },
});

export default function SearchPage() {
  const { t } = useTranslation("projects");
  const navigate = useNavigate();
  const [params, setParams] = useListSearchParams();
  const openWorkItem = useOpenWorkItem();
  const q = params.get("q") ?? "";
  const [draft, setDraft] = useState(q);

  useEffect(() => setDraft(q), [q]);

  const state = useAsync<SearchHit[]>(async () => {
    if (!q.trim()) return [];
    return (await api.get<SearchHit[]>(`/search?q=${encodeURIComponent(q.trim())}`)).data;
  }, [q]);

  // RDM-150: refresh results after an item drawer closes, once per batch.
  const eventInstanceId = useEventInstanceId();
  const overlayOpen = useItemOverlayOpen();
  useWorkItemUpdatedRefresh({
    instanceId: eventInstanceId,
    visible: !overlayOpen,
    onRefresh: state.reload,
  });

  const submit = () => {
    const next = draft.trim();
    if (next) setParams({ q: next });
  };

  // Work item hits open the drawer; record the search page as its backdrop.
  const openHit = (url: string) => {
    const match = /\/projects\/([^/]+)\/items\/([^/?#]+)/.exec(url);
    if (match) openWorkItem(decodeURIComponent(match[1]), decodeURIComponent(match[2]));
    else navigate(url);
  };

  return (
    <Page testId="page-search">
      <PageHeader title={t("search.title")} testId="search-header" />
      <Inline space="space.100" alignBlock="center" testId="search-bar">
        <Box style={{ width: 420 }}>
          <Textfield
            placeholder={t("search.placeholder")}
            value={draft}
            testId="search-input"
            autoFocus
            onChange={(e) => setDraft(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
        </Box>
        <Button appearance="primary" testId="search-submit" onClick={submit}>
          {t("search.submit")}
        </Button>
      </Inline>

      {!q.trim() ? (
        <Box testId="search-hint">
          <EmptyState
            header={t("search.hint")}
            description={t("search.hintDescription")}
          />
        </Box>
      ) : state.error ? (
        <ErrorState error={state.error} onRetry={state.reload} testId="search-error" />
      ) : state.loading ? (
        <Box xcss={styles.centered} testId="search-loading">
          <Spinner size="large" />
        </Box>
      ) : (state.data?.length ?? 0) === 0 ? (
        <Box testId="search-empty">
          <EmptyState
            header={t("search.empty")}
            description={t("search.emptyDescription", { query: q })}
          />
        </Box>
      ) : (
        <Stack space="space.100" testId="search-results">
          {state.data!.map((hit) => (
            <Box
              key={`${hit.entity_type}:${hit.entity_id}`}
              xcss={styles.card}
              style={cardBorder}
              testId={`search-hit-${hit.entity_type}-${hit.entity_id}`}
              role="button"
              tabIndex={0}
              onClick={() => openHit(hit.url)}
              onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  openHit(hit.url);
                }
              }}
            >
              <Inline space="space.100" alignBlock="center" shouldWrap>
                <Lozenge appearance="default">
                  {searchTypeLabel(hit.entity_type)}
                </Lozenge>
                <Text weight="medium">{hit.title}</Text>
                <Text color="color.text.subtlest" size="small">
                  {hit.project_key}
                  {hit.ref ? ` · ${hit.ref}` : ""}
                </Text>
              </Inline>
              {hit.snippet ? (
                <Box xcss={styles.snippet}>
                  <Text size="small" color="color.text.subtle">
                    {hit.snippet}
                  </Text>
                </Box>
              ) : null}
            </Box>
          ))}
        </Stack>
      )}
    </Page>
  );
}
