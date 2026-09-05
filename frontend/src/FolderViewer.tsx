import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  FileText,
  ScanSearch,
} from "lucide-react";
import {
  getFolder,
  getFolderOcr,
  OCR_TAB_LABELS,
  pageImageUrl,
  type FolderDetail,
  type OcrKind,
} from "./api";
import { ocrTextForFilename } from "./ocrPages";

type Props = {
  folderId: string;
  onBack: () => void;
};

type OutputMode = "ocr" | "imaging";

const OCR_TABS: OcrKind[] = ["preliminary", "final1", "final2"];

export default function FolderViewer({ folderId, onBack }: Props) {
  const [folder, setFolder] = useState<FolderDetail | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [outputMode, setOutputMode] = useState<OutputMode>("ocr");
  const [ocrTab, setOcrTab] = useState<OcrKind>("preliminary");
  const [ocrFullText, setOcrFullText] = useState("");
  const [loadingFolder, setLoadingFolder] = useState(true);
  const [loadingOcr, setLoadingOcr] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingFolder(true);
    setError(null);
    setPageIndex(0);
    setOutputMode("ocr");
    setOcrTab("preliminary");
    getFolder(folderId)
      .then((data) => {
        if (!cancelled) setFolder(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load folder");
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingFolder(false);
      });
    return () => {
      cancelled = true;
    };
  }, [folderId]);

  const page = folder?.pages[pageIndex] ?? null;

  useEffect(() => {
    if (!folder || outputMode !== "ocr") {
      setOcrFullText("");
      return;
    }
    let cancelled = false;
    setLoadingOcr(true);
    setOcrFullText("");
    getFolderOcr(folder.id, ocrTab)
      .then((data) => {
        if (!cancelled) setOcrFullText(data.text);
      })
      .catch((err) => {
        if (!cancelled) {
          setOcrFullText(
            err instanceof Error
              ? `No ${OCR_TAB_LABELS[ocrTab]} available.\n\n${err.message}`
              : "OCR unavailable",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingOcr(false);
      });
    return () => {
      cancelled = true;
    };
  }, [folder, ocrTab, outputMode]);

  const pageOcrText = useMemo(() => {
    if (!ocrFullText || !page) return "";
    if (ocrFullText.startsWith("No ") || ocrFullText === "OCR unavailable") {
      return ocrFullText;
    }
    const chunk = ocrTextForFilename(ocrFullText, page.filename);
    return chunk || `No OCR text found for ${page.filename}.`;
  }, [ocrFullText, page]);

  const pageCount = folder?.pages.length ?? 0;

  return (
    <div className="workspace">
      <div className="workspace-header">
        <div className="workspace-header-start">
          <button type="button" className="back-btn" onClick={onBack}>
            <ArrowLeft size={15} aria-hidden="true" />
            Back
          </button>
          <div className="workspace-title">
            <h1>{folder?.name ?? folderId}</h1>
            <p>
              {loadingFolder
                ? "Loading…"
                : `${pageCount} page${pageCount === 1 ? "" : "s"} · OCR ${folder?.ocr_processed ?? 0} · Imaging ${folder?.imaging_processed ?? 0}`}
            </p>
          </div>
        </div>

        <div className="mode-icon-group" role="group" aria-label="Output mode">
          <button
            type="button"
            className={`mode-icon-btn${outputMode === "ocr" ? " active" : ""}`}
            onClick={() => setOutputMode("ocr")}
            title="OCR"
            aria-label="OCR output"
            aria-pressed={outputMode === "ocr"}
          >
            <FileText size={18} aria-hidden="true" />
            <span>OCR</span>
          </button>
          <button
            type="button"
            className="mode-icon-btn"
            disabled
            title="Imaging (coming soon)"
            aria-label="Imaging output (disabled)"
          >
            <ScanSearch size={18} aria-hidden="true" />
            <span>Imaging</span>
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!error && (
        <div className="review-split">
          <section className="pane" aria-label="Page viewer">
            <div className="pane-header">
              <h2>Page{page ? ` · ${page.filename}` : ""}</h2>
              <div className="pager-nav">
                <button
                  type="button"
                  disabled={pageIndex <= 0}
                  onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeft size={16} />
                </button>
                <span className="pager-label">
                  {pageCount === 0 ? "—" : `${pageIndex + 1} / ${pageCount}`}
                </span>
                <button
                  type="button"
                  disabled={pageIndex >= pageCount - 1}
                  onClick={() => setPageIndex((i) => Math.min(pageCount - 1, i + 1))}
                  aria-label="Next page"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
            <div className="page-stage">
              {page ? (
                <img
                  src={pageImageUrl(folderId, page.page_number)}
                  alt={page.filename}
                />
              ) : (
                <div className="ocr-empty">
                  {loadingFolder ? "Loading pages…" : "No pages in this folder"}
                </div>
              )}
            </div>
            {folder && folder.pages.length > 0 && (
              <div className="filmstrip" role="listbox" aria-label="Page thumbnails">
                {folder.pages.map((p, idx) => (
                  <button
                    key={p.filename}
                    type="button"
                    className={`filmstrip-thumb${idx === pageIndex ? " active" : ""}`}
                    onClick={() => setPageIndex(idx)}
                    aria-label={`Go to ${p.filename}`}
                    aria-selected={idx === pageIndex}
                    title={p.filename}
                  >
                    <img
                      src={pageImageUrl(folderId, p.page_number)}
                      alt=""
                      loading="lazy"
                    />
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="pane" aria-label="Output panel">
            <div className="pane-header">
              <h2>
                {outputMode === "ocr" ? "OCR Output" : "Imaging Output"}
                {page ? (
                  <span className="ocr-page-label"> · {page.filename}</span>
                ) : null}
              </h2>
              {outputMode === "ocr" && (
                <div className="output-tabs" role="tablist" aria-label="OCR views">
                  {OCR_TABS.map((kind) => (
                    <button
                      key={kind}
                      type="button"
                      role="tab"
                      aria-selected={ocrTab === kind}
                      className={ocrTab === kind ? "active" : ""}
                      onClick={() => setOcrTab(kind)}
                    >
                      {OCR_TAB_LABELS[kind]}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="ocr-panel" role="tabpanel">
              {outputMode === "imaging" ? (
                <div className="ocr-empty">Imaging output is not available yet.</div>
              ) : loadingOcr ? (
                <div className="ocr-loading">Loading OCR output…</div>
              ) : (
                <pre>{pageOcrText || "No OCR text for this page."}</pre>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
