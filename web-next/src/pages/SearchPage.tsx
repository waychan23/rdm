import { useEffect, useState, type KeyboardEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

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
import { api } from "../lib/api";
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
});

const TYPE_LABEL: Record<string, string> = {
  work_item: "工作项",
  comment: "评论",
  message: "信件",
  artifact: "产出物",
};

export default function SearchPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [draft, setDraft] = useState(q);

  useEffect(() => setDraft(q), [q]);

  const state = useAsync<SearchHit[]>(async () => {
    if (!q.trim()) return [];
    return (await api.get<SearchHit[]>(`/search?q=${encodeURIComponent(q.trim())}`)).data;
  }, [q]);

  const submit = () => {
    const next = draft.trim();
    if (next) setParams({ q: next });
  };

  return (
    <Page testId="page-search">
      <PageHeader title="搜索" testId="search-header" />
      <Inline space="space.100" alignBlock="center" testId="search-bar">
        <Box style={{ width: 420 }}>
          <Textfield
            placeholder="搜索工作项、评论、信件、产出物"
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
          搜索
        </Button>
      </Inline>

      {!q.trim() ? (
        <Box testId="search-hint">
          <EmptyState header="输入关键词开始搜索" description="支持中文子串与多关键词。" />
        </Box>
      ) : state.error ? (
        <ErrorState error={state.error} onRetry={state.reload} testId="search-error" />
      ) : state.loading ? (
        <Box xcss={styles.centered} testId="search-loading">
          <Spinner size="large" />
        </Box>
      ) : (state.data?.length ?? 0) === 0 ? (
        <Box testId="search-empty">
          <EmptyState header="没有匹配结果" description={`没有找到与「${q}」相关的内容。`} />
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
              onClick={() => navigate(hit.url)}
              onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  navigate(hit.url);
                }
              }}
            >
              <Inline space="space.100" alignBlock="center" shouldWrap>
                <Lozenge appearance="default">{TYPE_LABEL[hit.entity_type] ?? hit.entity_type}</Lozenge>
                <Text weight="medium">{hit.title}</Text>
                <Text color="color.text.subtlest" size="small">
                  {hit.project_key}
                  {hit.ref ? ` · ${hit.ref}` : ""}
                </Text>
              </Inline>
              {hit.snippet ? (
                <Box paddingBlockStart="space.050">
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
