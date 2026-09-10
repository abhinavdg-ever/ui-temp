import { useMemo, useState } from "react";
import type {
  ImagingDocumentResponse,
  ImagingManifestDetails,
  ImagingPageResult,
  ImagingVerificationDetails,
} from "./api";

/** Doc Summary fallback when a page has no DOS and nothing to inherit. */
const DEFAULT_DOS = "2/2/2022";

function hasDos(value: string | null | undefined): value is string {
  return value != null && String(value).trim() !== "";
}

/**
 * Doc Summary only: missing DOS inherits the previous page's DOS;
 * if nothing precedes, use 2/2/2022.
 */
function fillDosForward(pages: ImagingPageResult[]): ImagingPageResult[] {
  let prevFrom: string | null = null;
  let prevTo: string | null = null;

  return [...pages]
    .sort((a, b) => a.pageNumber - b.pageNumber)
    .map((page) => {
      let dosFrom = hasDos(page.dosFrom) ? page.dosFrom.trim() : null;
      let dosTo = hasDos(page.dosTo) ? page.dosTo.trim() : null;

      if (!dosFrom && !dosTo) {
        dosFrom = prevFrom ?? DEFAULT_DOS;
        dosTo = prevTo ?? DEFAULT_DOS;
      } else {
        if (!dosFrom) dosFrom = dosTo ?? prevFrom ?? DEFAULT_DOS;
        if (!dosTo) dosTo = dosFrom ?? prevTo ?? DEFAULT_DOS;
      }

      prevFrom = dosFrom;
      prevTo = dosTo;
      return { ...page, dosFrom, dosTo };
    });
}

type ImagingTab = "page" | "doc";
type DocView = "values" | "confidence" | "rejection";

type Props = {
  tab: ImagingTab;
  loading: boolean;
  error: string | null;
  document: ImagingDocumentResponse | null;
  currentPage: ImagingPageResult | null;
  currentFileName: string | null;
};

function fmt(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Not Found";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

function fmtConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return "NA";
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(1)}%`;
}

function fmtPagesMatched(v: ImagingVerificationDetails): string {
  if (v.pagesMatched != null && v.pagesChecked != null) {
    return `${v.pagesMatched}/${v.pagesChecked}`;
  }
  if (v.pagesMatched != null) return String(v.pagesMatched);
  return "Not Found";
}

function DetailSection({
  title,
  rows,
  showConfidence = false,
}: {
  title: string;
  rows: { label: string; value: string; confidence?: string }[];
  showConfidence?: boolean;
}) {
  return (
    <section className="imaging-section">
      <h3 className="imaging-section-title">{title}</h3>
      <table className="imaging-detail-table">
        <thead>
          <tr>
            <th scope="col">Field</th>
            <th scope="col">Value</th>
            {showConfidence ? <th scope="col">Confidence</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              <td>{row.value}</td>
              {showConfidence ? (
                <td>{row.confidence ?? "Not Found"}</td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ManifestDetails({ manifest }: { manifest: ImagingManifestDetails }) {
  return (
    <div className="imaging-manifest-stack">
      <div className="imaging-manifest-row" role="group" aria-label="Manifest details">
        <span>
          <strong>Member Name:</strong> {fmt(manifest.member)}
        </span>
        <span>
          <strong>DOB:</strong> {fmt(manifest.dob)}
        </span>
        <span>
          <strong>Member ID:</strong> {fmt(manifest.memberId)}
        </span>
      </div>
    </div>
  );
}

function PageDetails({ page }: { page: ImagingPageResult }) {
  const memberConf = fmtConfidence(page.memberConfidence);
  const qualityConf = fmtConfidence(page.pageQualityConfidence);

  return (
    <div className="imaging-page-details">
      <section className="imaging-section">
        <h3 className="imaging-section-title">Member Extraction</h3>
        <table className="imaging-detail-table">
          <thead>
            <tr>
              <th scope="col">Field</th>
              <th scope="col">Value</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">Extracted Name</th>
              <td>{fmt(page.memberName)}</td>
              <td>{memberConf}</td>
            </tr>
            <tr>
              <th scope="row">Extracted DOB</th>
              <td>{fmt(page.memberDob)}</td>
              <td>{memberConf}</td>
            </tr>
            <tr>
              <th scope="row">Member ID</th>
              <td>{fmt(page.memberId)}</td>
              <td>{memberConf}</td>
            </tr>
          </tbody>
        </table>
      </section>
      <DetailSection
        title="Page Quality & Orientation"
        showConfidence
        rows={[
          {
            label: "Printed / Handwritten",
            value: fmt(page.handwrittenOrPrinted),
            confidence: fmtConfidence(
              page.handwrittenOrPrintedConfidence ?? page.pageQualityConfidence,
            ),
          },
          {
            label: "Orientation Angle (Page)",
            value: fmt(page.orientationAngle),
            confidence: qualityConf,
          },
          {
            label: "Tilt Angle (Text)",
            value: fmt(page.tiltAngle),
            confidence: qualityConf,
          },
          {
            label: "Mirrored (Text)",
            value: fmt(page.mirrored),
            confidence: qualityConf,
          },
        ]}
      />
      <DetailSection
        title="DOS Extraction"
        showConfidence
        rows={[
          {
            label: "DOS From",
            value: fmt(page.dosFrom),
            confidence: fmtConfidence(page.dosConfidence),
          },
          {
            label: "DOS To",
            value: fmt(page.dosTo),
            confidence: fmtConfidence(page.dosConfidence),
          },
        ]}
      />
      <DetailSection
        title="Page Classification"
        showConfidence
        rows={[
          {
            label: "Page Type",
            value: fmt(page.pageType),
            confidence: fmtConfidence(page.pageTypeConfidence),
          },
        ]}
      />
    </div>
  );
}

function RejectionRulesTable({
  rows,
}: {
  rows: ImagingVerificationDetails[];
}) {
  if (rows.length === 0) {
    return (
      <div className="ocr-empty">No member verification summary for this chart.</div>
    );
  }

  return (
    <table className="imaging-summary-table imaging-rejection-table">
      <thead>
        <tr>
          <th scope="col">Component</th>
          <th scope="col">Status</th>
          <th scope="col">Matched Name</th>
          <th scope="col">Pages</th>
          <th scope="col">Conf.</th>
          <th scope="col">Decision Reason</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((v, idx) => (
          <tr key={`${v.finalStatus ?? "row"}-${idx}`}>
            <td>Member Verification</td>
            <td>{fmt(v.finalStatus)}</td>
            <td>{fmt(v.matchedName)}</td>
            <td>{fmtPagesMatched(v)}</td>
            <td>{fmtConfidence(v.matchedConfidence)}</td>
            <td className="imaging-decision-reason">{fmt(v.decisionReason)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DocSummary({
  pages,
  verifications,
}: {
  pages: ImagingPageResult[];
  verifications: ImagingVerificationDetails[];
}) {
  const [view, setView] = useState<DocView>("values");
  const rows = useMemo(() => fillDosForward(pages), [pages]);
  const showConfidence = view === "confidence";

  return (
    <div className="imaging-doc-summary">
      <div className="output-tabs imaging-doc-tabs" role="tablist" aria-label="Doc summary view">
        <button
          type="button"
          role="tab"
          aria-selected={view === "values"}
          className={view === "values" ? "active" : ""}
          onClick={() => setView("values")}
        >
          Values
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "confidence"}
          className={view === "confidence" ? "active" : ""}
          onClick={() => setView("confidence")}
        >
          With Confidence
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={view === "rejection"}
          className={view === "rejection" ? "active" : ""}
          onClick={() => setView("rejection")}
        >
          Rejection Rules
        </button>
      </div>

      {view === "rejection" ? (
        <RejectionRulesTable rows={verifications} />
      ) : (
        <table className="imaging-summary-table">
          <thead>
            <tr>
              <th scope="col">Page #</th>
              <th scope="col">File</th>
              <th scope="col">Extracted Name</th>
              <th scope="col">Extracted DOB</th>
              <th scope="col">Member ID</th>
              <th scope="col">HW/Printed</th>
              <th scope="col">Orient.</th>
              <th scope="col">Tilt</th>
              <th scope="col">Mirrored</th>
              <th scope="col">DOS From</th>
              <th scope="col">DOS To</th>
              <th scope="col">Page Type</th>
              {showConfidence ? (
                <>
                  <th scope="col">Member Conf.</th>
                  <th scope="col">Quality Conf.</th>
                  <th scope="col">DOS Conf.</th>
                  <th scope="col">Type Conf.</th>
                </>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={`${p.pageNumber}-${p.fileName}`}>
                <td>{p.pageNumber}</td>
                <td className="imaging-mono">{p.fileName}</td>
                <td>{fmt(p.memberName)}</td>
                <td>{fmt(p.memberDob)}</td>
                <td>{fmt(p.memberId)}</td>
                <td>{fmt(p.handwrittenOrPrinted)}</td>
                <td>{fmt(p.orientationAngle)}</td>
                <td>{fmt(p.tiltAngle)}</td>
                <td>{fmt(p.mirrored)}</td>
                <td>{fmt(p.dosFrom)}</td>
                <td>{fmt(p.dosTo)}</td>
                <td>{fmt(p.pageType)}</td>
                {showConfidence ? (
                  <>
                    <td>{fmtConfidence(p.memberConfidence)}</td>
                    <td>{fmtConfidence(p.pageQualityConfidence)}</td>
                    <td>{fmtConfidence(p.dosConfidence)}</td>
                    <td>{fmtConfidence(p.pageTypeConfidence)}</td>
                  </>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function ImagingPanel({
  tab,
  loading,
  error,
  document,
  currentPage,
  currentFileName,
}: Props) {
  if (loading) {
    return <div className="ocr-loading">Loading imaging results…</div>;
  }
  if (error) {
    return <div className="ocr-empty">{error}</div>;
  }
  if (!document || document.pages.length === 0) {
    return <div className="ocr-empty">No imaging results for this folder.</div>;
  }

  const manifest = document.manifest ?? {
    member: null,
    dob: null,
    memberId: null,
  };
  const verifications =
    document.verifications && document.verifications.length > 0
      ? document.verifications
      : document.verification
        ? [document.verification]
        : [];

  if (tab === "doc") {
    return (
      <div className="imaging-panel-stack">
        <ManifestDetails manifest={manifest} />
        <DocSummary pages={document.pages} verifications={verifications} />
      </div>
    );
  }

  if (!currentPage) {
    return (
      <div className="imaging-panel-stack">
        <ManifestDetails manifest={manifest} />
        <div className="ocr-empty">
          {currentFileName
            ? `No imaging row for ${currentFileName}.`
            : "Select a page to view imaging details."}
        </div>
      </div>
    );
  }

  return (
    <div className="imaging-panel-stack">
      <ManifestDetails manifest={manifest} />
      <PageDetails page={currentPage} />
    </div>
  );
}

export type { ImagingTab };
