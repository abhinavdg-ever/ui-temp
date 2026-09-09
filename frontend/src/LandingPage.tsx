import { useEffect, useMemo, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderOpen,
  Inbox,
  RefreshCw,
  ScanSearch,
  Search,
} from "lucide-react";
import {
  listFolders,
  OCR_STATUS_LABELS,
  type FolderSummary,
  type OcrRunStatus,
} from "./api";

const PAGE_SIZE = 15;

type Props = {
  onView: (folderId: string) => void;
  onOpenFileViewer?: () => void;
};

type SortKey = "filename" | "pages" | "updated";
type SortDir = "asc" | "desc";

function fmtUpdated(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  }).format(d);
}

function statusClass(status: OcrRunStatus): string {
  switch (status) {
    case "COMPLETED":
      return "status-pill status-completed";
    case "IN_PROGRESS":
      return "status-pill status-progress";
    case "FAILED":
      return "status-pill status-failed";
    default:
      return "status-pill status-queued";
  }
}

function compareFolders(a: FolderSummary, b: FolderSummary, key: SortKey, dir: SortDir): number {
  const sign = dir === "asc" ? 1 : -1;
  if (key === "filename") {
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) * sign;
  }
  if (key === "pages") {
    if (a.page_count !== b.page_count) return (a.page_count - b.page_count) * sign;
    return a.name.localeCompare(b.name) * sign;
  }
  const at = a.last_updated_at ? Date.parse(a.last_updated_at) : 0;
  const bt = b.last_updated_at ? Date.parse(b.last_updated_at) : 0;
  if (at !== bt) return (at - bt) * sign;
  return a.name.localeCompare(b.name) * sign;
}

export default function LandingPage({ onView, onOpenFileViewer }: Props) {
  const [folders, setFolders] = useState<FolderSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("updated");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [statusFilter, setStatusFilter] = useState<"ALL" | OcrRunStatus>("ALL");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listFolders();
      setFolders(data);
      setPage(1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let rows = folders;
    if (q) {
      rows = rows.filter((f) => f.name.toLowerCase().includes(q));
    }
    if (statusFilter !== "ALL") {
      rows = rows.filter((f) => f.ocr_status === statusFilter);
    }
    return [...rows].sort((a, b) => compareFolders(a, b, sortKey, sortDir));
  }, [folders, query, sortKey, sortDir, statusFilter]);

  const totals = useMemo(() => {
    const pages = filtered.reduce((sum, f) => sum + f.page_count, 0);
    const ocr = filtered.reduce((sum, f) => sum + f.ocr_processed, 0);
    return { folders: filtered.length, pages, ocr };
  }, [filtered]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [query, sortKey, sortDir, statusFilter]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const pageFolders = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, page]);

  const rangeStart = filtered.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, filtered.length);

  const pageNumbers = useMemo(() => {
    const maxButtons = 7;
    if (totalPages <= maxButtons) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const pages = new Set<number>([1, totalPages, page]);
    for (let d = 1; pages.size < maxButtons - 1; d++) {
      if (page - d >= 1) pages.add(page - d);
      if (page + d <= totalPages) pages.add(page + d);
    }
    return [...pages].sort((a, b) => a - b);
  }, [page, totalPages]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(key === "filename" ? "asc" : "desc");
    }
  }

  function sortIndicator(key: SortKey): string {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  return (
    <div className="landing">
      <div className="landing-home">
        <div className="landing-intro">
          <div>
            <h1>History</h1>
            <p>Browse processed folders, and view OCR and Imaging Pipeline Results.</p>
          </div>
          {onOpenFileViewer ? (
            <button type="button" className="landing-file-viewer-btn" onClick={onOpenFileViewer}>
              <FolderOpen size={15} aria-hidden="true" />
              File Viewer
            </button>
          ) : null}
        </div>

        {folders.length > 0 && (
          <div className="landing-stats" aria-label="Summary">
            <div className="landing-stat">
              <span className="landing-stat-value">{totals.folders}</span>
              <span className="landing-stat-label">folders</span>
            </div>
            <div className="landing-stat-divider" />
            <div className="landing-stat">
              <span className="landing-stat-value">{totals.pages}</span>
              <span className="landing-stat-label">pages</span>
            </div>
            <div className="landing-stat-divider" />
            <div className="landing-stat">
              <span className="landing-stat-value">{totals.ocr}</span>
              <span className="landing-stat-label">OCR processed</span>
            </div>
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}

        <section className="landing-history" aria-label="History">
          <div className="landing-history-header">
            <div className="landing-history-title">
              <h2>History</h2>
              <span className="landing-history-count">{filtered.length}</span>
            </div>

            <div className="landing-toolbar">
              <label className="landing-search">
                <Search size={14} aria-hidden="true" />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search file / folder…"
                  aria-label="Search folders"
                />
              </label>

              <label className="landing-select-wrap">
                <span>Status</span>
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as "ALL" | OcrRunStatus)}
                  aria-label="Filter by status"
                >
                  <option value="ALL">All</option>
                  <option value="QUEUED">Queued</option>
                  <option value="IN_PROGRESS">In Progress</option>
                  <option value="COMPLETED">OCR Completed</option>
                  <option value="FAILED">Failed</option>
                </select>
              </label>

              <button
                type="button"
                className="landing-icon-btn"
                onClick={() => void load()}
                title="Refresh"
                aria-label="Refresh history"
                disabled={loading}
              >
                <RefreshCw size={15} />
              </button>
            </div>
          </div>

          <div className="landing-history-scroll">
            <table className="landing-history-table">
              <thead>
                <tr>
                  <th>
                    <button
                      type="button"
                      className={`th-sort${sortKey === "filename" ? " active" : ""}`}
                      onClick={() => toggleSort("filename")}
                    >
                      Folder{sortIndicator("filename")}
                    </button>
                  </th>
                  <th>
                    <button
                      type="button"
                      className={`th-sort${sortKey === "pages" ? " active" : ""}`}
                      onClick={() => toggleSort("pages")}
                    >
                      Pages{sortIndicator("pages")}
                    </button>
                  </th>
                  <th>OCR</th>
                  <th>Imaging</th>
                  <th>Status</th>
                  <th>
                    <button
                      type="button"
                      className={`th-sort${sortKey === "updated" ? " active" : ""}`}
                      onClick={() => toggleSort("updated")}
                    >
                      Last Updated{sortIndicator("updated")}
                    </button>
                  </th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading && folders.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="landing-history-empty">
                      <div className="landing-empty-state">
                        <div className="landing-empty-icon">
                          <RefreshCw size={18} />
                        </div>
                        <h3>Loading history…</h3>
                      </div>
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="landing-history-empty">
                      <div className="landing-empty-state">
                        <div className="landing-empty-icon">
                          <Inbox size={18} />
                        </div>
                        <h3>{folders.length === 0 ? "No history found" : "No matching folders"}</h3>
                        <p>
                          {folders.length === 0
                            ? "Add folders under DATA_ROOT with pages/ and ocr/ outputs."
                            : "Try a different search or status filter."}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  pageFolders.map((folder) => (
                    <tr key={folder.id}>
                      <td className="landing-col-name" title={folder.name}>
                        {folder.name}
                      </td>
                      <td className="landing-col-num">{folder.page_count}</td>
                      <td className="landing-col-num">{folder.ocr_processed}</td>
                      <td className="landing-col-num">{folder.imaging_processed}</td>
                      <td>
                        <span className={statusClass(folder.ocr_status)}>
                          {OCR_STATUS_LABELS[folder.ocr_status]}
                        </span>
                      </td>
                      <td className="landing-col-updated">
                        {fmtUpdated(folder.last_updated_at)}
                      </td>
                      <td>
                        <div className="landing-row-actions">
                          <button
                            type="button"
                            className="action-icon-btn"
                            onClick={() => onView(folder.id)}
                            title="View OCR"
                            aria-label={`View OCR for ${folder.name}`}
                          >
                            <FileText size={16} aria-hidden="true" />
                            OCR
                          </button>
                          <button
                            type="button"
                            className="action-icon-btn"
                            disabled
                            title="Imaging (coming soon)"
                            aria-label={`View Imaging for ${folder.name} (disabled)`}
                          >
                            <ScanSearch size={16} aria-hidden="true" />
                            Imaging
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {filtered.length > 0 && (
            <div className="landing-pagination" aria-label="History pagination">
              <span className="landing-pagination-meta">
                {rangeStart}–{rangeEnd} of {filtered.length}
              </span>
              <div className="landing-pagination-controls">
                <button
                  type="button"
                  className="landing-page-btn"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft size={14} />
                </button>
                {pageNumbers.map((n, idx) => {
                  const prev = pageNumbers[idx - 1];
                  const showEllipsis = prev != null && n - prev > 1;
                  return (
                    <span key={n} className="landing-page-num-wrap">
                      {showEllipsis && <span className="landing-page-ellipsis">…</span>}
                      <button
                        type="button"
                        className={`landing-page-num${n === page ? " active" : ""}`}
                        onClick={() => setPage(n)}
                        aria-label={`Page ${n}`}
                        aria-current={n === page ? "page" : undefined}
                      >
                        {n}
                      </button>
                    </span>
                  );
                })}
                <button
                  type="button"
                  className="landing-page-btn"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  aria-label="Next page"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
