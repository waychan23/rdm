import { useState } from "react";

import Button from "@atlaskit/button/default/button";
import ModalDialog, {
  ModalBody,
  ModalFooter,
  ModalHeader,
  ModalTitle,
  ModalTransition,
} from "@atlaskit/modal-dialog";
import Textfield from "@atlaskit/textfield";
import Select from "@atlaskit/select";
import { Stack } from "@atlaskit/primitives";

export const ARTIFACT_KINDS = ["link", "doc", "design", "api_doc", "repo", "other"];

interface Props {
  open: boolean;
  onClose: () => void;
  onSave: (artifact: { kind: string; label: string; url: string }) => Promise<void> | void;
}

export default function ArtifactDialog({ open, onClose, onSave }: Props) {
  const [kind, setKind] = useState("link");
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [saving, setSaving] = useState(false);

  const options = ARTIFACT_KINDS.map((k) => ({ label: k, value: k }));

  return (
    <ModalTransition>
      {open && (
        <ModalDialog onClose={onClose} width="440px">
          <ModalHeader>
            <ModalTitle>挂载产出物</ModalTitle>
          </ModalHeader>
          <ModalBody>
            <Stack space="space.150">
              <Stack space="space.050">
                <label htmlFor="art-kind">类型</label>
                <Select
                  inputId="art-kind"
                  options={options}
                  value={options.find((o) => o.value === kind)}
                  onChange={(opt) => opt && setKind((opt as { value: string }).value)}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="art-label">标题</label>
                <Textfield
                  id="art-label"
                  value={label}
                  onChange={(e) => setLabel(e.currentTarget.value)}
                />
              </Stack>
              <Stack space="space.050">
                <label htmlFor="art-url">URL</label>
                <Textfield
                  id="art-url"
                  value={url}
                  placeholder="https://…"
                  onChange={(e) => setUrl(e.currentTarget.value)}
                />
              </Stack>
            </Stack>
          </ModalBody>
          <ModalFooter>
            <Button appearance="subtle" onClick={onClose}>
              取消
            </Button>
            <Button
              appearance="primary"
              isLoading={saving}
              onClick={async () => {
                if (!label.trim() || !url.trim()) return;
                setSaving(true);
                await onSave({ kind, label: label.trim(), url: url.trim() });
                setLabel("");
                setUrl("");
              }}
            >
              保存
            </Button>
          </ModalFooter>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
