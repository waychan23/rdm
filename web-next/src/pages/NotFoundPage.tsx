import { useNavigate } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";

export default function NotFoundPage() {
  const navigate = useNavigate();
  return (
    <EmptyState
      header="页面不存在（404）"
      description="链接可能已失效，或工作项已被删除。"
      testId="page-not-found"
      primaryAction={
        <Button
          appearance="primary"
          testId="not-found-home"
          onClick={() => navigate("/projects")}
        >
          回到项目
        </Button>
      }
    />
  );
}
