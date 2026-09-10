export type OcrRunStatus = "QUEUED" | "IN_PROGRESS" | "COMPLETED" | "FAILED";

export type FolderSummary = {
  id: string;
  name: string;
  page_count: number;
  ocr_processed: number;
  imaging_processed: number;
  ocr_status: OcrRunStatus;
  last_updated_at: string | null;
};

export type PageSummary = {
  page_number: number;
  filename: string;
  image_url: string;
  has_preliminary_ocr: boolean;
  has_final1_ocr: boolean;
  has_final2_ocr: boolean;
  has_imaging?: boolean;
};

export type FolderDetail = FolderSummary & {
  pages: PageSummary[];
};

/** preliminary = Tess (_prelim), final1 = OSS (_final1), final2 = AzDocInt (_final2) */
export type OcrKind = "preliminary" | "final1" | "final2";

export type OutputMode = "ocr" | "imaging";

export type OcrTextResponse = {
  folder_id: string;
  kind: OcrKind;
  text: string;
};

export type ImagingPageResult = {
  pageNumber: number;
  fileName: string;
  memberName: string | null;
  memberDob: string | null;
  memberId: string | null;
  memberConfidence: number | null;
  handwrittenOrPrinted: string | null;
  orientationAngle: number | null;
  tiltAngle: number | null;
  mirrored: boolean | null;
  pageQualityConfidence: number | null;
  dosFrom: string | null;
  dosTo: string | null;
  dosConfidence: number | null;
  docDosFrom?: string | null;
  docDosTo?: string | null;
  pageType: string | null;
  pageTypeConfidence: number | null;
};

export type ImagingManifestDetails = {
  member: string | null;
  dob: string | null;
  memberId: string | null;
};

export type ImagingDocumentResponse = {
  folder_id: string;
  manifest: ImagingManifestDetails;
  pages: ImagingPageResult[];
};

export type BlobAuthMode = "entra" | "sas";

export type AppConfig = {
  data_mode: string;
  file_viewer_blob_enabled: boolean;
  blob_auth_mode: BlobAuthMode;
  blob_account_url: string;
  blob_container: string;
  blob_path_template: string;
  blob_entra_ready: boolean;
  blob_auth_required: boolean;
  blob_sas_configured: boolean;
};

export const OCR_TAB_LABELS: Record<OcrKind, string> = {
  preliminary: "Preliminary (Tess)",
  final1: "Final (OSS)",
  final2: "Final (AzDocInt)",
};

export const OCR_STATUS_LABELS: Record<OcrRunStatus, string> = {
  QUEUED: "Queued",
  IN_PROGRESS: "In Progress",
  COMPLETED: "OCR Completed",
  FAILED: "Failed",
};

async function api<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export function getAppConfig(): Promise<AppConfig> {
  return api("/api/config");
}

export function listFolders(): Promise<FolderSummary[]> {
  return api("/api/folders");
}

export function getFolder(folderId: string): Promise<FolderDetail> {
  return api(`/api/folders/${encodeURIComponent(folderId)}`);
}

export function getFolderOcr(folderId: string, kind: OcrKind): Promise<OcrTextResponse> {
  const params = new URLSearchParams({ kind });
  return api(`/api/folders/${encodeURIComponent(folderId)}/ocr?${params}`);
}

export function getFolderImaging(folderId: string): Promise<ImagingDocumentResponse> {
  return api(`/api/folders/${encodeURIComponent(folderId)}/imaging`);
}

export function pageImageUrl(folderId: string, pageNumber: number): string {
  return `/api/folders/${encodeURIComponent(folderId)}/pages/${pageNumber}/image`;
}

export function blobPageImageUrl(folderId: string, pageNumber: number): string {
  return `/api/blob/${encodeURIComponent(folderId)}/pages/${pageNumber}/image`;
}
