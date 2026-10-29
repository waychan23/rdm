import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import Select from "@atlaskit/select";

import { api } from "../lib/api";
import { portalMenuProps } from "../lib/portalMenu";
import type { WorkItem } from "../types";

export interface WorkItemOption {
  label: string;
  value: string;
  id: string;
  display_id: string;
  title: string;
  kind: string;
  status: string;
  row_version: number;
}

interface BaseProps {
  projectKey: string;
  allowedKinds: string[];
  excludeIds?: string[];
  excludeStatuses?: string[];
  backlogOnly?: boolean;
  placeholder?: string;
  isDisabled?: boolean;
  testId?: string;
  inputId?: string;
}

interface SingleProps extends BaseProps {
  isMulti?: false;
  value: WorkItemOption | null;
  onChange: (value: WorkItemOption | null) => void;
}

interface MultiProps extends BaseProps {
  isMulti: true;
  value: WorkItemOption[];
  onChange: (value: WorkItemOption[]) => void;
}

type Props = SingleProps | MultiProps;

function toOption(item: WorkItem): WorkItemOption {
  return {
    label: `${item.display_id} · ${item.title}`,
    value: item.display_id,
    id: item.id,
    display_id: item.display_id,
    title: item.title,
    kind: item.kind,
    status: item.status,
    row_version: item.row_version,
  };
}

export default function WorkItemPicker(props: Props) {
  const {
    projectKey,
    allowedKinds,
    excludeIds = [],
    excludeStatuses = [],
    backlogOnly = false,
    placeholder = "搜索工作项",
    isDisabled = false,
    testId,
    inputId,
  } = props;
  const [options, setOptions] = useState<WorkItemOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const timer = useRef<number | null>(null);
  // Callers commonly pass inline arrays; keep the latest values in a ref and
  // only re-run load when the joined keys actually change.
  const config = useRef({ allowedKinds, excludeIds, excludeStatuses });
  config.current = { allowedKinds, excludeIds, excludeStatuses };
  const kindsKey = allowedKinds.join(",");
  const excludeKey = excludeIds.join(",");
  const statusKey = excludeStatuses.join(",");

  const load = useCallback(
    async (term: string) => {
      const { allowedKinds, excludeIds, excludeStatuses } = config.current;
      if (allowedKinds.length === 0) {
        setOptions([]);
        return;
      }
      setLoading(true);
      try {
        const responses = await Promise.all(
          allowedKinds.map((kind) => {
            const params = new URLSearchParams({ limit: "20", kind });
            if (term.trim()) params.set("q", term.trim());
            if (backlogOnly) params.set("backlog", "true");
            return api.get<WorkItem[]>(
              `/projects/${projectKey}/work-items?${params.toString()}`,
            );
          }),
        );
        const seen = new Set<string>();
        const next: WorkItemOption[] = [];
        for (const response of responses) {
          for (const item of response.data) {
            if (seen.has(item.id)) continue;
            if (excludeIds.includes(item.id)) continue;
            if (excludeStatuses.includes(item.status)) continue;
            seen.add(item.id);
            next.push(toOption(item));
          }
        }
        setOptions(next.sort((a, b) => a.value.localeCompare(b.value)));
      } catch {
        setOptions([]);
      } finally {
        setLoading(false);
      }
    },
    [backlogOnly, excludeKey, kindsKey, projectKey, statusKey],
  );

  useEffect(() => {
    void load("");
  }, [load]);

  const onInputChange = (input: string, meta: { action: string }) => {
    if (meta.action !== "input-change") return;
    setQuery(input);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void load(input), 250);
  };

  const mergedOptions = useMemo(() => {
    const current = props.isMulti ? props.value : props.value ? [props.value] : [];
    const byValue = new Map(options.map((option) => [option.value, option]));
    for (const option of current) {
      if (!byValue.has(option.value)) byValue.set(option.value, option);
    }
    return [...byValue.values()];
  }, [options, props.isMulti, props.value]);

  if (props.isMulti) {
    return (
      <Select<WorkItemOption, true>
        {...portalMenuProps}
        inputId={inputId}
        isMulti
        isLoading={loading}
        options={mergedOptions}
        value={props.value}
        placeholder={placeholder}
        isDisabled={isDisabled}
        filterOption={null}
        inputValue={query}
        onInputChange={onInputChange}
        onChange={(value) => {
          setQuery("");
          props.onChange([...(value as WorkItemOption[])]);
        }}
        testId={testId}
      />
    );
  }
  return (
    <Select<WorkItemOption>
      {...portalMenuProps}
      inputId={inputId}
      isClearable
      isLoading={loading}
      options={mergedOptions}
      value={props.value}
      placeholder={placeholder}
      isDisabled={isDisabled}
      filterOption={null}
      inputValue={query}
      onInputChange={onInputChange}
      onChange={(value) => {
        setQuery("");
        props.onChange((value as WorkItemOption | null) ?? null);
      }}
      testId={testId}
    />
  );
}
