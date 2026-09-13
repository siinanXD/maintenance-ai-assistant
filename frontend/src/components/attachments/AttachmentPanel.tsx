import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";

import {
  attachmentObjectUrl,
  deleteAttachment,
  loadAttachments,
  uploadAttachment,
  type Attachment,
  type AttachmentEntityType
} from "./attachmentApi";

type AttachmentPanelProps = {
  readonly entityType: AttachmentEntityType;
  readonly entityId: number;
  readonly writable: boolean;
};

/**
 * Return a short human-readable file size.
 */
function sizeLabel(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Render one stored photo or PDF with its protected preview.
 */
function AttachmentTile(props: {
  readonly attachment: Attachment;
  readonly writable: boolean;
  readonly onDelete: (attachment: Attachment) => void;
}): ReactNode {
  const [previewUrl, setPreviewUrl] = useState("");

  useEffect(() => {
    if (!props.attachment.is_image) return undefined;
    let url = "";
    let cancelled = false;
    attachmentObjectUrl(props.attachment)
      .then((objectUrl) => {
        url = objectUrl;
        if (cancelled) URL.revokeObjectURL(objectUrl);
        else setPreviewUrl(objectUrl);
      })
      .catch(() => setPreviewUrl(""));
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [props.attachment]);

  /**
   * Open the file in a new tab through a temporary object URL.
   */
  async function openFile(): Promise<void> {
    const url = await attachmentObjectUrl(props.attachment);
    window.open(url, "_blank", "noopener");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }

  return (
    <li className="attachment-tile">
      <button className="attachment-preview" type="button" onClick={() => void openFile()} aria-label={`${props.attachment.filename} öffnen`}>
        {props.attachment.is_image && previewUrl ? <img alt="" src={previewUrl} /> : <span className="attachment-file-mark">{props.attachment.is_image ? "Foto" : "PDF"}</span>}
      </button>
      <div className="attachment-meta">
        <strong title={props.attachment.filename}>{props.attachment.filename}</strong>
        <small>{sizeLabel(props.attachment.size_bytes)}{props.attachment.uploaded_by?.username ? ` · ${props.attachment.uploaded_by.username}` : ""}</small>
      </div>
      {props.writable ? (
        <button className="btn btn-ghost btn-xs" type="button" onClick={() => props.onDelete(props.attachment)}>Entfernen</button>
      ) : null}
    </li>
  );
}

/**
 * Collapsible photo and PDF section for incident and task cards.
 * Loads its list only when opened, so long catalogs stay fast.
 */
export function AttachmentPanel({ entityType, entityId, writable }: AttachmentPanelProps): ReactNode {
  const [attachments, setAttachments] = useState<Attachment[] | null>(null);
  const [status, setStatus] = useState({ text: "", error: false });
  const [busy, setBusy] = useState(false);
  const cameraInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  /**
   * Reload the list from the API.
   */
  async function refresh(): Promise<void> {
    try {
      setAttachments(await loadAttachments(entityType, entityId));
    } catch (error) {
      setStatus({ text: error instanceof Error ? error.message : "Dateien konnten nicht geladen werden.", error: true });
      setAttachments([]);
    }
  }

  /**
   * Upload the selected files one after another.
   */
  async function handleFiles(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const files = Array.from(event.currentTarget.files || []);
    event.currentTarget.value = "";
    if (!files.length) return;
    setBusy(true);
    setStatus({ text: files.length > 1 ? `${files.length} Dateien werden hochgeladen…` : "Wird hochgeladen…", error: false });
    try {
      for (const file of files) {
        await uploadAttachment(entityType, entityId, file);
      }
      setStatus({ text: files.length > 1 ? `${files.length} Dateien gespeichert.` : "Gespeichert.", error: false });
      await refresh();
    } catch (error) {
      setStatus({ text: error instanceof Error ? error.message : "Upload fehlgeschlagen.", error: true });
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  /**
   * Delete one attachment after confirmation.
   */
  async function handleDelete(attachment: Attachment): Promise<void> {
    if (!window.confirm(`„${attachment.filename}“ entfernen?`)) return;
    try {
      await deleteAttachment(attachment.id);
      setStatus({ text: "Entfernt.", error: false });
      await refresh();
    } catch (error) {
      setStatus({ text: error instanceof Error ? error.message : "Datei konnte nicht entfernt werden.", error: true });
    }
  }

  return (
    <details
      className="attachment-panel"
      onToggle={(event) => {
        if (event.currentTarget.open && attachments === null) void refresh();
      }}
    >
      <summary>
        Fotos &amp; Dateien{attachments && attachments.length ? <span className="attachment-count">{attachments.length}</span> : null}
      </summary>
      <div className="attachment-body">
        {writable ? (
          <div className="attachment-actions">
            <button className="btn btn-outline btn-sm" disabled={busy} type="button" onClick={() => cameraInput.current?.click()}>Foto aufnehmen</button>
            <button className="btn btn-ghost btn-sm" disabled={busy} type="button" onClick={() => fileInput.current?.click()}>Datei wählen</button>
            <input accept="image/*" capture="environment" hidden ref={cameraInput} type="file" onChange={(event) => void handleFiles(event)} />
            <input accept="image/jpeg,image/png,image/webp,application/pdf" hidden multiple ref={fileInput} type="file" onChange={(event) => void handleFiles(event)} />
          </div>
        ) : null}
        {status.text ? <p className={`panel-meta${status.error ? " is-error" : ""}`} role="status">{status.text}</p> : null}
        {attachments === null ? <p className="panel-meta">Wird geladen…</p> : null}
        {attachments && !attachments.length ? <p className="panel-meta">Noch keine Fotos oder Dateien.</p> : null}
        {attachments && attachments.length ? (
          <ul className="attachment-grid">
            {attachments.map((attachment) => (
              <AttachmentTile attachment={attachment} key={attachment.id} writable={writable} onDelete={(item) => void handleDelete(item)} />
            ))}
          </ul>
        ) : null}
      </div>
    </details>
  );
}
