import Pagination from "@atlaskit/pagination";
import IconButton from "@atlaskit/button/icon/button";
import ChevronDownIcon from "@atlaskit/icon/core/chevron-down";
import ChevronRightIcon from "@atlaskit/icon/core/chevron-right";
import { Text } from "@atlaskit/primitives/compiled";

import PersonCell from "../components/PersonCell";
import PriorityMark from "../components/PriorityMark";
import TypeKindIcon from "../components/TypeKindIcon";
import { formatDate } from "../lib/format";
import type { WorkItem } from "../types";
import StatusLozenge from "./status";
import "../styles/table.css";

export interface WorkItemRowView {
  item: WorkItem;
  /** Nesting level in the hierarchical view (0 = top level). */
  depth?: number;
  childCount?: number;
  collapsed?: boolean;
}

interface Props {
  rows: WorkItemRowView[];
  total: number;
  page: number;
  pageCount: number;
  onOpen: (item: WorkItem) => void;
  onPageChange: (page: number) => void;
  /** Present in the hierarchical view; renders expand/collapse toggles. */
  onToggle?: (item: WorkItem) => void;
  countNote?: string;
}

export default function WorkItemTable({
  rows,
  total,
  page,
  pageCount,
  onOpen,
  onPageChange,
  onToggle,
  countNote,
}: Props) {
  return (
    <div
      style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}
      data-testid="work-item-table-container"
    >
      <table className="rdm-table" aria-label="工作项列表" data-testid="work-item-table">
        <thead>
          <tr>
            <th scope="col" className="col-title">
              标题
            </th>
            <th scope="col" className="col-status">
              状态
            </th>
            <th scope="col" className="col-priority">
              优先级
            </th>
            <th scope="col" className="col-person">
              负责人
            </th>
            <th scope="col" className="col-date">
              创建时间
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ item: row, depth = 0, childCount = 0, collapsed = false }) => (
            <tr
              key={row.id}
              data-clickable="true"
              tabIndex={0}
              data-testid={`work-item-row-${row.display_id}`}
              onClick={() => onOpen(row)}
              onKeyDown={(e) => {
                // Ignore keys bubbling from the row's own buttons.
                if (e.target !== e.currentTarget) return;
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpen(row);
                }
              }}
            >
              <td>
                <span
                  className="cell-title"
                  style={{
                    paddingInlineStart: `calc(var(--ds-space-200, 16px) * ${depth})`,
                  }}
                >
                  {onToggle ? (
                    childCount > 0 ? (
                      <IconButton
                        icon={(iconProps) =>
                          collapsed ? (
                            <ChevronRightIcon {...iconProps} />
                          ) : (
                            <ChevronDownIcon {...iconProps} />
                          )
                        }
                        label={`${collapsed ? "展开" : "折叠"} ${row.display_id} 的子项`}
                        appearance="subtle"
                        spacing="compact"
                        testId={`work-item-toggle-${row.display_id}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          onToggle(row);
                        }}
                      />
                    ) : (
                      <span className="rdm-tree-toggle-spacer" aria-hidden />
                    )
                  ) : null}
                  <TypeKindIcon kind={row.kind} />
                  <span className="display-id">{row.display_id}</span>
                  <span className="title-text">{row.title}</span>
                </span>
              </td>
              <td>
                <StatusLozenge status={row.status} />
              </td>
              <td>
                <PriorityMark priority={row.priority} />
              </td>
              <td>
                <PersonCell name={row.assignee?.name} />
              </td>
              <td>
                <span className="cell-meta">{formatDate(row.created_at)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="rdm-pager" data-testid="work-item-pager">
        <Text size="small" color="color.text.subtlest" testId="work-item-total">
          共 {total} 条{countNote ? ` · ${countNote}` : ""}
        </Text>
        <Pagination
          pages={Array.from({ length: pageCount }, (_, i) => i + 1)}
          selectedIndex={page - 1}
          onChange={(_e, p) => onPageChange(Number(p))}
        />
      </div>
    </div>
  );
}
