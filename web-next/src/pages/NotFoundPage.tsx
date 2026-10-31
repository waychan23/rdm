import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import Button from "@atlaskit/button/default/button";
import EmptyState from "@atlaskit/empty-state";

export default function NotFoundPage() {
  const { t } = useTranslation("nav");
  const navigate = useNavigate();
  return (
    <EmptyState
      header={t("notFound.header")}
      description={t("notFound.description")}
      testId="page-not-found"
      primaryAction={
        <Button
          appearance="primary"
          testId="not-found-home"
          onClick={() => navigate("/projects")}
        >
          {t("notFound.back")}
        </Button>
      }
    />
  );
}
