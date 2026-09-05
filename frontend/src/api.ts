export type FolderSummary = {
  id: string;
  name: string;
  page_count: number;
  ocr_processed: number;
  imaging_processed: number;
  last_updated_at: string | null;
};

export type PageSummary = {
  page_number: number;
  filename: string;
  image_url: string;
  has_preliminary_ocr: boolean;
  has_final_ocr: boolean;
};

export type FolderDetail = FolderSummary & {
  pages: PageSummary[];
};

export type OcrKind = "preliminary" | "final";

export type OcrTextResponse = {
  folder_id: string;
  kind: OcrKind;
  text: string;
};

async function api<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
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

export function pageImageUrl(folderId: string, pageNumber: number): string {
  return `/api/folders/${encodeURIComponent(folderId)}/pages/${pageNumber}/image`;
}
