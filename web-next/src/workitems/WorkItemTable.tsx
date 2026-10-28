import Pagination from "@atlaskit/pagination";
import { Text } from "@atlaskit/primitives";

import PersonCell from "../components/PersonCell";
import PriorityMark from "../components/PriorityMark";
import TypeKindIcon from "../components/TypeKindIcon";
import type { WorkItem } from "../types";
import StatusLozenge from "./status";
import "../styles/table.css";

interface Props {
  items: WorkItem[];
  total: number;
  page: number;
  pageSize: number;
  onOpen: (item: WorkItem) => void;
  onPageChange: (page: number) => void;
}

export default function WorkItemTable({
  items,
  total,
  page,
  pageSize,
  onOpen,
  onPageChange,
}: Props) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <table className="rdm-table">
        <thead>
          <tr>
            <th className="col-title">标题</th>
            <th style={{ width: 140 }}>状态</th>
            <th style={{ width: 110 }}>优先级</th>
            <th style={{ width: 180 }}>负责人</th>
            <th style={{ width: 160 }}>创建时间</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.id} onClick={() => onOpen(row)}>
              <td>
                <span className="cell-title">
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
                <span className="cell-meta">{row.created_at.slice(0, 10)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="rdm-pager">
        <Text size="small" color="color.text.subtlest">
          共 {total} 条
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
