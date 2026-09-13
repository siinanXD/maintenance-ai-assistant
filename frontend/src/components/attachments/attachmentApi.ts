import { apiRequest, fetchAuthorizedBlob } from "../../api/client";
import { listData, unwrapData } from "../../api/payload";

export type AttachmentEntityType = "error" | "task";

export type Attachment = {
  readonly id: number;
  readonly filename: string;
  readonly content_type: string;
  readonly size_bytes: number;
  readonly is_image: boolean;
  readonly created_at: string;
  readonly file_url: string;
  readonly uploaded_by?: { readonly username?: string } | null;
};

/**
 * Load the attachments of one incident or task.
 */
export async function loadAttachments(entityType: AttachmentEntityType, entityId: number): Promise<Attachment[]> {
  const params = new URLSearchParams({ entity_type: entityType, entity_id: String(entityId) });
  return listData<Attachment>(await apiRequest<unknown>(`/api/v1/attachments?${params.toString()}`));
}

/**
 * Upload one photo or PDF.
 */
export async function uploadAttachment(entityType: AttachmentEntityType, entityId: number, file: File): Promise<Attachment> {
  const body = new FormData();
  body.set("entity_type", entityType);
  body.set("entity_id", String(entityId));
  body.set("file", file);
  return unwrapData<Attachment>(await apiRequest<unknown>("/api/v1/attachments", { method: "POST", body }));
}

/**
 * Delete one attachment.
 */
export async function deleteAttachment(attachmentId: number): Promise<void> {
  await apiRequest<unknown>(`/api/v1/attachments/${attachmentId}`, { method: "DELETE" });
}

/**
 * Return an object URL for a stored file; the caller revokes it.
 */
export async function attachmentObjectUrl(attachment: Attachment): Promise<string> {
  return URL.createObjectURL(await fetchAuthorizedBlob(attachment.file_url));
}
