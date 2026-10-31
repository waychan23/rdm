import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { ClipboardEvent, DragEvent, KeyboardEvent } from "react";

import IconButton from "@atlaskit/button/icon/button";
import Spinner from "@atlaskit/spinner";
import Select from "@atlaskit/select";
import TextArea from "@atlaskit/textarea";
import { Inline, Text } from "@atlaskit/primitives/compiled";
import AngleBracketsIcon from "@atlaskit/icon/core/angle-brackets";
import ImageIcon from "@atlaskit/icon/core/image";
import LinkIcon from "@atlaskit/icon/core/link";
import ListBulletedIcon from "@atlaskit/icon/core/list-bulleted";
import ListNumberedIcon from "@atlaskit/icon/core/list-numbered";
import MentionIcon from "@atlaskit/icon/core/mention";
import TextBoldIcon from "@atlaskit/icon/core/text-bold";
import TextHeadingIcon from "@atlaskit/icon/core/text-heading";
import TextItalicIcon from "@atlaskit/icon/core/text-italic";
import TextStrikethroughIcon from "@atlaskit/icon/core/text-strikethrough";
import TextStyleIcon from "@atlaskit/icon/core/text-style";

import MarkdownText from "./MarkdownText";
import TextButton from "./TextButton";
import { api, errorCause } from "../lib/api";
import { useNotify } from "../lib/flags";
import { flattenMembers } from "../lib/members";
import { portalMenuProps } from "../lib/portalMenu";
import type { Attachment, OrgUser, ProjectMemberRow } from "../types";
import "../styles/markdown-editor.css";

export interface MarkdownImageClick {
  src: string;
  alt: string;
  original: string;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  projectKey: string;
  placeholder?: string;
  minimumRows?: number;
  isDisabled?: boolean;
  autoFocus?: boolean;
  testId?: string;
  onSubmit?: () => void;
  onImageClick?: (image: MarkdownImageClick) => void;
  onUploadingChange?: (uploading: boolean) => void;
}

type MentionOption = { label: string; value: string };

export default function MarkdownEditor({
  value,
  onChange,
  projectKey,
  placeholder,
  minimumRows = 3,
  isDisabled = false,
  autoFocus = false,
  testId,
  onSubmit,
  onImageClick,
  onUploadingChange,
}: Props) {
  const { t } = useTranslation("components");
  const notify = useNotify();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"edit" | "preview">("edit");
  const [uploading, setUploading] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [members, setMembers] = useState<MentionOption[]>([]);
  const [mentionOpen, setMentionOpen] = useState(false);

  useEffect(() => {
    onUploadingChange?.(uploading > 0);
  }, [uploading, onUploadingChange]);

  useEffect(() => {
    let alive = true;
    api
      .get<ProjectMemberRow[]>(`/projects/${projectKey}/members`)
      .then((res) => {
        if (!alive) return;
        setMembers(
          flattenMembers(res.data).map((m: OrgUser) => ({ label: m.name, value: m.name })),
        );
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [projectKey]);

  const selection = () => {
    const el = textareaRef.current;
    const start = el?.selectionStart ?? value.length;
    const end = el?.selectionEnd ?? start;
    return { start, end };
  };

  const insertAt = useCallback(
    (start: number, end: number, text: string) => {
      const next = value.slice(0, start) + text + value.slice(end);
      onChange(next);
      requestAnimationFrame(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.focus();
        const pos = start + text.length;
        el.setSelectionRange(pos, pos);
      });
    },
    [onChange, value],
  );

  const wrap = (before: string, after: string, placeholderText: string | undefined = undefined) => {
    const { start, end } = selection();
    const selected = value.slice(start, end) || placeholderText || t("editor.textPlaceholder");
    insertAt(start, end, `${before}${selected}${after}`);
  };

  const prefix = (prefixText: string) => {
    const { start } = selection();
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    insertAt(lineStart, start, prefixText);
  };

  const uploadImages = async (files: File[]) => {
    const images = files.filter((file) => file.type.startsWith("image/"));
    if (images.length === 0) return;
    const { start, end } = selection();
    setUploading((n) => n + images.length);
    const inserted: string[] = [];
    try {
      for (const file of images) {
        const form = new FormData();
        form.append("file", file);
        form.append("owner_type", "project");
        form.append("owner_ref", projectKey);
        form.append("state", "temp");
        const res = await api.upload<Attachment>(
          `/projects/${projectKey}/attachments`,
          form,
        );
        const alt = file.name.replace(/[[\]]/g, "");
        inserted.push(`![${alt}](${res.data.download_url})`);
      }
      if (inserted.length > 0) {
        const text = `\n${inserted.join("\n")}\n`;
        insertAt(start, end, text);
      }
    } catch (e) {
      notify.error(t("editor.uploadFailed"), errorCause(e)?.message);
    } finally {
      setUploading((n) => Math.max(0, n - images.length));
    }
  };

  const onPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files);
    if (files.some((file) => file.type.startsWith("image/"))) {
      event.preventDefault();
      void uploadImages(files);
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const files = Array.from(event.dataTransfer.files);
    if (files.some((file) => file.type.startsWith("image/"))) {
      void uploadImages(files);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      onSubmit?.();
    }
  };

  return (
    <div
      className={`rdm-md-editor${dragging ? " rdm-md-editor-dragging" : ""}`}
      onDragOver={(e) => {
        if (Array.from(e.dataTransfer.items).some((i) => i.kind === "file")) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      data-testid={testId ? `${testId}-editor` : undefined}
    >
      <div className="rdm-md-editor-toolbar" data-testid={testId ? `${testId}-toolbar` : undefined}>
        <IconButton
          icon={(p) => <TextBoldIcon {...p} />}
          label={t("editor.bold")}
          appearance="subtle"
          spacing="compact"
          onClick={() => wrap("**", "**")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <TextItalicIcon {...p} />}
          label={t("editor.italic")}
          appearance="subtle"
          spacing="compact"
          onClick={() => wrap("_", "_")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <TextStrikethroughIcon {...p} />}
          label={t("editor.strikethrough")}
          appearance="subtle"
          spacing="compact"
          onClick={() => wrap("~~", "~~")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <TextHeadingIcon {...p} />}
          label={t("editor.heading")}
          appearance="subtle"
          spacing="compact"
          onClick={() => prefix("## ")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <LinkIcon {...p} />}
          label={t("editor.link")}
          appearance="subtle"
          spacing="compact"
          onClick={() => wrap("[", "](https://)", t("editor.linkText"))}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <ListBulletedIcon {...p} />}
          label={t("editor.bulletList")}
          appearance="subtle"
          spacing="compact"
          onClick={() => prefix("- ")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <ListNumberedIcon {...p} />}
          label={t("editor.orderedList")}
          appearance="subtle"
          spacing="compact"
          onClick={() => prefix("1. ")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <TextStyleIcon {...p} />}
          label={t("editor.inlineCode")}
          appearance="subtle"
          spacing="compact"
          onClick={() => wrap("`", "`", "code")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <AngleBracketsIcon {...p} />}
          label={t("editor.codeBlock")}
          appearance="subtle"
          spacing="compact"
          onClick={() => wrap("\n```\n", "\n```\n", "code")}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <ImageIcon {...p} />}
          label={t("editor.insertImage")}
          appearance="subtle"
          spacing="compact"
          onClick={() => fileInputRef.current?.click()}
          isDisabled={isDisabled}
        />
        <IconButton
          icon={(p) => <MentionIcon {...p} />}
          label={t("editor.mention")}
          appearance="subtle"
          spacing="compact"
          onClick={() => setMentionOpen((open) => !open)}
          isDisabled={isDisabled}
        />
        <div className="rdm-md-editor-spacer" />
        {uploading > 0 && (
          <Inline space="space.050" alignBlock="center">
            <Spinner size="small" />
            <Text size="small" color="color.text.subtlest">
              {t("editor.uploadingImage")}
            </Text>
          </Inline>
        )}
        <TextButton onClick={() => setMode(mode === "edit" ? "preview" : "edit")}>
          {mode === "edit" ? t("editor.preview") : t("editor.edit")}
        </TextButton>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          void uploadImages(Array.from(e.target.files ?? []));
          e.currentTarget.value = "";
        }}
      />

      {mentionOpen && (
        <div className="rdm-md-editor-mention">
          <Select<MentionOption>
            {...portalMenuProps}
            spacing="compact"
            placeholder={t("editor.mentionPlaceholder")}
            options={members}
            value={null}
            autoFocus
            onChange={(opt) => {
              if (!opt) return;
              const { start, end } = selection();
              insertAt(start, end, `@${(opt as MentionOption).value} `);
              setMentionOpen(false);
            }}
          />
        </div>
      )}

      {mode === "preview" ? (
        <div className="rdm-md-editor-preview" data-testid={testId ? `${testId}-preview` : undefined}>
          {value.trim() ? (
            <MarkdownText source={value} onImageClick={onImageClick} />
          ) : (
            <Text size="small" color="color.text.subtlest">
              {t("editor.empty")}
            </Text>
          )}
        </div>
      ) : (
        <TextArea
          ref={textareaRef}
          value={value}
          minimumRows={minimumRows}
          placeholder={placeholder}
          isDisabled={isDisabled}
          autoFocus={autoFocus}
          testId={testId}
          onChange={(e) => onChange(e.currentTarget.value)}
          onPaste={onPaste}
          onKeyDown={onKeyDown}
        />
      )}
      {dragging && <div className="rdm-md-editor-drop-hint">{t("editor.dropHint")}</div>}
    </div>
  );
}
