import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  FileText,
  Maximize2,
  Minimize2,
  PanelLeftClose,
  PanelLeftOpen,
  ScanSearch,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import {
  getFolder,
  getFolderImaging,
  getFolderOcr,
  OCR_TAB_LABELS,
  pageImageUrl,
  type FolderDetail,
  type ImagingDocumentResponse,
  type ImagingPageResult,
  type OcrKind,
  type OutputMode,
} from "./api";
import ImagingPanel, { type ImagingTab } from "./ImagingPanel";
import { ocrTextForFilename } from "./ocrPages";
import FullscreenPageChrome from "./FullscreenPageChrome";
import { useImagePan } from "./useImagePan";
import { usePageViewerHotkeys } from "./usePageViewerHotkeys";

type Props = {
  folderId: string;
  initialMode?: OutputMode;
  onBack: () => void;
  onModeChange?: (mode: OutputMode) => void;
};

const OCR_TABS: OcrKind[] = ["preliminary", "final1", "final2"];
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.25;

const KIND_FILE_SUFFIX: Record<OcrKind, string> = {
  preliminary: "prelim",
  final1: "final1",
  final2: "final2",
};

function downloadTextFile(filename: string, text: string, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadJsonFile(filename: string, data: unknown) {
  downloadTextFile(filename, JSON.stringify(data, null, 2), "application/json;charset=utf-8");
}

function isUsableOcrText(text: string): boolean {
  if (!text.trim()) return false;
  if (text.startsWith("No ")) return false;
  if (text === "OCR unavailable") return false;
  if (text.startsWith("No OCR text found")) return false;
  return true;
}

function findImagingPage(
  doc: ImagingDocumentResponse | null,
  page: { page_number: number; filename: string } | null,
): ImagingPageResult | null {
  if (!doc || !page) return null;
  const byFile = doc.pages.find(
    (p) => p.fileName.toLowerCase() === page.filename.toLowerCase(),
  );
  if (byFile) return byFile;
  return doc.pages.find((p) => p.pageNumber === page.page_number) ?? null;
}

export default function FolderViewer({
  folderId,
  initialMode = "ocr",
  onBack,
  onModeChange,
}: Props) {
  const [folder, setFolder] = useState<FolderDetail | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [outputMode, setOutputMode] = useState<OutputMode>(initialMode);
  const [ocrTab, setOcrTab] = useState<OcrKind>("preliminary");
  const [imagingTab, setImagingTab] = useState<ImagingTab>("page");
  const [ocrFullText, setOcrFullText] = useState("");
  const [imagingDoc, setImagingDoc] = useState<ImagingDocumentResponse | null>(null);
  const [loadingFolder, setLoadingFolder] = useState(true);
  const [loadingOcr, setLoadingOcr] = useState(false);
  const [loadingImaging, setLoadingImaging] = useState(false);
  const [imagingError, setImagingError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [outputExpanded, setOutputExpanded] = useState(false);
  const pageStageRef = useRef<HTMLDivElement>(null);
  const {
    resetPan,
    imageStyle,
    stageProps,
    stageClassName,
  } = useImagePan(zoom, `${folderId}:${pageIndex}`);

  function resetZoom() {
    setZoom(1);
    resetPan();
  }

  useEffect(() => {
    setOutputMode(initialMode);
  }, [initialMode]);

  useEffect(() => {
    let cancelled = false;
    setLoadingFolder(true);
    setError(null);
    setPageIndex(0);
    setOcrTab("preliminary");
    setImagingTab("page");
    setImagingDoc(null);
    setZoom(1);
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

  useEffect(() => {
    function onFsChange() {
      setIsFullscreen(document.fullscreenElement === pageStageRef.current);
    }
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const page = folder?.pages[pageIndex] ?? null;

  useEffect(() => {
    if (!folder || outputMode !== "ocr") {
      setOcrFullText("");
      return;
    }
    let cancelled = false;
    setLoadingOcr(true);
    setOcrFullText("");
    setCopied(false);
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

  useEffect(() => {
    if (!folder || outputMode !== "imaging") {
      return;
    }
    let cancelled = false;
    setLoadingImaging(true);
    setImagingError(null);
    getFolderImaging(folder.id)
      .then((data) => {
        if (!cancelled) setImagingDoc(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setImagingDoc(null);
          setImagingError(
            err instanceof Error ? err.message : "Failed to load imaging results",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingImaging(false);
      });
    return () => {
      cancelled = true;
    };
  }, [folder, outputMode]);

  const pageOcrText = useMemo(() => {
    if (!ocrFullText || !page) return "";
    if (ocrFullText.startsWith("No ") || ocrFullText === "OCR unavailable") {
      return ocrFullText;
    }
    const chunk = ocrTextForFilename(ocrFullText, page.filename);
    return chunk || `No OCR text found for ${page.filename}.`;
  }, [ocrFullText, page]);

  const imagingPage = useMemo(
    () => findImagingPage(imagingDoc, page),
    [imagingDoc, page],
  );

  const canUseFull = isUsableOcrText(ocrFullText);
  const pageCount = folder?.pages.length ?? 0;
  const folderName = folder?.name ?? folderId;
  const suffix = KIND_FILE_SUFFIX[ocrTab];

  function changeMode(mode: OutputMode) {
    setOutputMode(mode);
    onModeChange?.(mode);
  }

  function downloadFullOcr() {
    if (!canUseFull) return;
    downloadTextFile(`${folderName}_${suffix}.txt`, ocrFullText);
  }

  async function copyFullOcr() {
    if (!canUseFull) return;
    try {
      await navigator.clipboard.writeText(ocrFullText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  function downloadImagingDocJson() {
    if (!imagingDoc) return;
    downloadJsonFile(`${folderName}_imaging.json`, imagingDoc);
  }

  function downloadImagingDocCsv() {
    if (!imagingDoc) return;
    const headers = [
      "pageNumber",
      "fileName",
      "memberName",
      "memberDob",
      "memberId",
      "memberConfidence",
      "handwrittenOrPrinted",
      "orientationAngle",
      "tiltAngle",
      "mirrored",
      "pageQualityConfidence",
      "dos",
      "dosConfidence",
      "pageType",
      "pageTypeConfidence",
      "manifestMember",
      "manifestDob",
      "manifestMemberId",
    ];
    const esc = (v: unknown) => {
      const s = v === null || v === undefined ? "" : String(v);
      if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
      return s;
    };
    const m = imagingDoc.manifest;
    const rows = imagingDoc.pages.map((p) =>
      [
        p.pageNumber,
        p.fileName,
        p.memberName,
        p.memberDob,
        p.memberId,
        p.memberConfidence,
        p.handwrittenOrPrinted,
        p.orientationAngle,
        p.tiltAngle,
        p.mirrored,
        p.pageQualityConfidence,
        p.dos,
        p.dosConfidence,
        p.pageType,
        p.pageTypeConfidence,
        m?.member ?? "",
        m?.dob ?? "",
        m?.memberId ?? "",
      ]
        .map(esc)
        .join(","),
    );
    downloadTextFile(
      `${folderName}_imaging.csv`,
      [headers.join(","), ...rows].join("\n"),
      "text/csv;charset=utf-8",
    );
  }

  function zoomBy(delta: number) {
    setZoom((z) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round((z + delta) * 100) / 100)));
  }

  async function toggleFullscreen() {
    const el = pageStageRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement === el) {
        await document.exitFullscreen();
      } else {
        await el.requestFullscreen();
      }
    } catch {
      /* ignore */
    }
  }

  function exitFullscreen() {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    }
  }

  usePageViewerHotkeys({
    enabled: pageCount > 0,
    pageCount,
    setPageIndex,
    zoomBy,
    setZoom,
    zoomStep: ZOOM_STEP,
    isFullscreen,
    onExitFullscreen: exitFullscreen,
  });

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
            onClick={() => changeMode("ocr")}
            title="OCR"
            aria-label="OCR output"
            aria-pressed={outputMode === "ocr"}
          >
            <FileText size={18} aria-hidden="true" />
            <span>OCR</span>
          </button>
          <button
            type="button"
            className={`mode-icon-btn${outputMode === "imaging" ? " active" : ""}`}
            onClick={() => changeMode("imaging")}
            title="Imaging"
            aria-label="Imaging output"
            aria-pressed={outputMode === "imaging"}
          >
            <ScanSearch size={18} aria-hidden="true" />
            <span>Imaging</span>
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!error && (
        <div className={`review-split${outputExpanded ? " output-expanded" : ""}`}>
          {!outputExpanded && (
          <section className="pane" aria-label="Page viewer">
            <div className="pane-header">
              <h2>Page{page ? ` · ${page.filename}` : ""}</h2>
              <div className="page-toolbar">
                <div className="zoom-controls" role="group" aria-label="Zoom">
                  <button
                    type="button"
                    onClick={() => zoomBy(-ZOOM_STEP)}
                    disabled={zoom <= ZOOM_MIN}
                    aria-label="Zoom out"
                    title="Zoom out"
                  >
                    <ZoomOut size={15} />
                  </button>
                  <button
                    type="button"
                    className="zoom-reset"
                    onClick={resetZoom}
                    title="Reset zoom"
                  >
                    {Math.round(zoom * 100)}%
                  </button>
                  <button
                    type="button"
                    onClick={() => zoomBy(ZOOM_STEP)}
                    disabled={zoom >= ZOOM_MAX}
                    aria-label="Zoom in"
                    title="Zoom in"
                  >
                    <ZoomIn size={15} />
                  </button>
                </div>
                <button
                  type="button"
                  className="fullscreen-btn"
                  onClick={() => void toggleFullscreen()}
                  aria-label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
                  title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
                >
                  {isFullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                </button>
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
            </div>
            <div
              className={`page-stage${isFullscreen ? " is-fullscreen" : ""}${stageClassName ? ` ${stageClassName}` : ""}`}
              ref={pageStageRef}
              {...stageProps}
            >
              {page ? (
                <img
                  src={pageImageUrl(folderId, page.page_number)}
                  alt={page.filename}
                  draggable={false}
                  onPointerDown={stageProps.onPointerDown}
                  style={imageStyle}
                />
              ) : (
                <div className="ocr-empty">
                  {loadingFolder ? "Loading pages…" : "No pages in this folder"}
                </div>
              )}
              {isFullscreen ? (
                <FullscreenPageChrome
                  pageIndex={pageIndex}
                  pageCount={pageCount}
                  zoom={zoom}
                  zoomMin={ZOOM_MIN}
                  zoomMax={ZOOM_MAX}
                  label={page?.filename}
                  onZoomOut={() => zoomBy(-ZOOM_STEP)}
                  onZoomIn={() => zoomBy(ZOOM_STEP)}
                  onZoomReset={resetZoom}
                  onPrev={() => {
                    setPageIndex((i) => Math.max(0, i - 1));
                    resetZoom();
                  }}
                  onNext={() => {
                    setPageIndex((i) => Math.min(pageCount - 1, i + 1));
                    resetZoom();
                  }}
                  onExitFullscreen={exitFullscreen}
                />
              ) : null}
            </div>
            {folder && folder.pages.length > 0 && (
              <div className="filmstrip" role="listbox" aria-label="Page thumbnails">
                {folder.pages.map((p, idx) => (
                  <button
                    key={p.filename}
                    type="button"
                    className={`filmstrip-thumb${idx === pageIndex ? " active" : ""}`}
                    onClick={() => {
                      setPageIndex(idx);
                      setZoom(1);
                    }}
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
          )}

          <section className="pane" aria-label="Output panel">
            <div className="pane-header pane-header-wrap">
              <div className="pane-header-main">
                <button
                  type="button"
                  className="pane-expand-btn"
                  onClick={() => setOutputExpanded((v) => !v)}
                  title={
                    outputExpanded
                      ? "Show page viewer"
                      : "Expand output to full width"
                  }
                  aria-label={
                    outputExpanded
                      ? "Show page viewer"
                      : "Expand output to full width"
                  }
                  aria-pressed={outputExpanded}
                >
                  {outputExpanded ? (
                    <PanelLeftOpen size={16} aria-hidden="true" />
                  ) : (
                    <PanelLeftClose size={16} aria-hidden="true" />
                  )}
                </button>
                <h2>
                  {outputMode === "ocr" ? "OCR Output" : "Imaging Output"}
                  {page && outputMode === "ocr" ? (
                    <span className="ocr-page-label"> · {page.filename}</span>
                  ) : null}
                </h2>
              </div>
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
              {outputMode === "imaging" && (
                <div className="output-tabs" role="tablist" aria-label="Imaging views">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={imagingTab === "page"}
                    className={imagingTab === "page" ? "active" : ""}
                    onClick={() => setImagingTab("page")}
                  >
                    Page Details
                  </button>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={imagingTab === "doc"}
                    className={imagingTab === "doc" ? "active" : ""}
                    onClick={() => setImagingTab("doc")}
                  >
                    Doc Summary
                  </button>
                </div>
              )}
            </div>
            <div className="ocr-panel" role="tabpanel">
              {outputMode === "imaging" ? (
                <ImagingPanel
                  tab={imagingTab}
                  loading={loadingImaging}
                  error={imagingError}
                  document={imagingDoc}
                  currentPage={imagingPage}
                  currentFileName={page?.filename ?? null}
                />
              ) : loadingOcr ? (
                <div className="ocr-loading">Loading OCR output…</div>
              ) : (
                <pre>{pageOcrText || "No OCR text for this page."}</pre>
              )}
            </div>
            {outputMode === "ocr" && (
              <div className="ocr-panel-footer">
                <button
                  type="button"
                  className="ocr-footer-btn"
                  disabled={loadingOcr || !canUseFull}
                  onClick={() => void copyFullOcr()}
                  title={`Copy full ${OCR_TAB_LABELS[ocrTab]} text`}
                >
                  <Copy size={14} aria-hidden="true" />
                  {copied ? "Copied" : "Copy"}
                </button>
                <button
                  type="button"
                  className="ocr-footer-btn primary"
                  disabled={loadingOcr || !canUseFull}
                  onClick={downloadFullOcr}
                  title={`Download full ${OCR_TAB_LABELS[ocrTab]} file`}
                >
                  <Download size={14} aria-hidden="true" />
                  Download
                </button>
              </div>
            )}
            {outputMode === "imaging" && (
              <div className="ocr-panel-footer">
                <button
                  type="button"
                  className="ocr-footer-btn"
                  disabled={loadingImaging || !imagingDoc}
                  onClick={downloadImagingDocCsv}
                  title="Download document imaging as CSV"
                >
                  <Download size={14} aria-hidden="true" />
                  Document CSV
                </button>
                <button
                  type="button"
                  className="ocr-footer-btn primary"
                  disabled={loadingImaging || !imagingDoc}
                  onClick={downloadImagingDocJson}
                  title="Download document imaging as JSON"
                >
                  <Download size={14} aria-hidden="true" />
                  Document JSON
                </button>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
