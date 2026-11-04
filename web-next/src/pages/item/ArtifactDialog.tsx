import { useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import { Stack } from "@atlaskit/primitives/compiled";
import Select from "@atlaskit/select";
import Textfield from "@atlaskit/textfield";
import { useTranslation } from "react-i18next";

import FormField from "../../components/FormField";
import { artifactKindLabel } from "../../lib/labels";

export const ARTIFACT_KINDS = ["link", "doc", "design", "api_doc", "repo", "other"];

interface Props {
  open: boolean;
  onClose: () => void;
  onSave: (artifact: { kind: string; label: string; url: string }) => Promise<void> | void;
}

export default function ArtifactDialog({ open, onClose, onSave }: Props) {
  const { t } = useTranslation("item");
  const [kind, setKind] = useState("link");
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const options = ARTIFACT_KINDS.map((k) => ({ label: artifactKindLabel(k), value: k }));

  return (
    <ModalTransition>
      {open && (
        <ModalDialog
          onClose={onClose}
          width="440px"
          // Backdrop clicks must not discard a half-filled form (RDM-163).
          shouldCloseOnOverlayClick={false}
          testId="artifact-dialog"
        >
          <ModalHeader>
            <ModalTitle>{t("artifact.title")}</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <FormField label={t("artifact.kind")} htmlFor="art-kind">
                <Select
                  inputId="art-kind"
                  options={options}
                  value={options.find((o) => o.value === kind)}
                  onChange={(opt) => opt && setKind((opt as { value: string }).value)}
                />
              </FormField>
              <FormField label={t("artifact.label")} htmlFor="art-label">
                <Textfield
                  id="art-label"
                  value={label}
                  testId="artifact-label"
                  onChange={(e) => setLabel(e.currentTarget.value)}
                />
              </FormField>
              <FormField label={t("artifact.url")} htmlFor="art-url">
                <Textfield
                  id="art-url"
                  value={url}
                  placeholder="https://…"
                  testId="artifact-url"
                  onChange={(e) => setUrl(e.currentTarget.value)}
                />
              </FormField>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose} testId="artifact-cancel">
              {t("artifact.cancel")}
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              testId="artifact-submit"
              onClick={async () => {
                if (!label.trim() || !url.trim()) return;
                setSaving(true);
                try {
                  await onSave({ kind, label: label.trim(), url: url.trim() });
                  setLabel("");
                  setUrl("");
                } finally {
                  setSaving(false);
                }
              }}
            >
              {t("artifact.save")}
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
