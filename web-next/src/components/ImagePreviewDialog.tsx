import ModalDialog, { ModalTransition } from "@atlaskit/modal-dialog";

interface Props {
  open: boolean;
  src: string | null;
  alt?: string;
  onClose: () => void;
}

export default function ImagePreviewDialog({ open, src, alt, onClose }: Props) {
  return (
    <ModalTransition>
      {open && src && (
        <ModalDialog onClose={onClose} width="x-large" testId="image-preview-dialog">
          <div className="rdm-image-preview">
            <img src={src} alt={alt ?? ""} />
          </div>
        </ModalDialog>
      )}
    </ModalTransition>
  );
}
