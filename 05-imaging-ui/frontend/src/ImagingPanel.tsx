import { useState } from "react";
import type {
  ImagingDocumentResponse,
  ImagingManifestDetails,
  ImagingPageResult,
  ImagingVerificationDetails,
} from "./api";

type ImagingTab = "page" | "doc";

type Props = {
  tab: ImagingTab;
  loading: boolean;
  error: string | null;
  document: ImagingDocumentResponse | null;
  currentPage: ImagingPageResult | null;
  currentFileName: string | null;
};

function fmt(value: string | number | boolean | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

function fmtConfidence(value: number | null | undefined): string {
  if (value === null || value === undefined) return "NA";
  if (value <= 1) return `${Math.round(value * 100)}%`;
  return `${value}%`;
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
              {showConfidence ? <td>{row.confidence ?? "—"}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ManifestDetails({
  manifest,
  verification,
}: {
  manifest: ImagingManifestDetails;
  verification?: ImagingVerificationDetails | null;
}) {
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
      {verification ? (
        <div
          className="imaging-manifest-row imaging-verification-row"
          role="group"
          aria-label="Member verification summary"
        >
          <span>
            <strong>Status:</strong> {fmt(verification.finalStatus)}
          </span>
          <span>
            <strong>Match conf.:</strong>{" "}
            {fmtConfidence(verification.matchedConfidence)}
          </span>
          <span>
            <strong>Pages:</strong>{" "}
            {verification.pagesMatched != null && verification.pagesChecked != null
              ? `${verification.pagesMatched}/${verification.pagesChecked}`
              : "—"}
          </span>
          {verification.decisionReason ? (
            <span className="imaging-verification-reason">
              <strong>Reason:</strong> {verification.decisionReason}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function PageDetails({ page }: { page: ImagingPageResult }) {
  const memberConf = fmtConfidence(page.memberConfidence);
  const qualityConf = fmtConfidence(page.pageQualityConfidence);

  return (
    <div className="imaging-page-details">
      <section className="imaging-section">
        <h3 className="imaging-section-title">Member Verification</h3>
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
              <th scope="row">Member Name</th>
              <td>{fmt(page.memberName)}</td>
              <td>{memberConf}</td>
            </tr>
            <tr>
              <th scope="row">Member DOB</th>
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
        title="Printed / Handwritten"
        showConfidence
        rows={[
          {
            label: "Type",
            value: fmt(page.handwrittenOrPrinted),
            confidence: fmtConfidence(
              page.handwrittenOrPrintedConfidence ?? page.pageQualityConfidence,
            ),
          },
        ]}
      />
      <DetailSection
        title="Page Quality & Orientation"
        showConfidence
        rows={[
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

function DocSummary({ pages }: { pages: ImagingPageResult[] }) {
  const [showConfidence, setShowConfidence] = useState(false);

  return (
    <div className="imaging-doc-summary">
      <div className="output-tabs imaging-doc-tabs" role="tablist" aria-label="Doc summary view">
        <button
          type="button"
          role="tab"
          aria-selected={!showConfidence}
          className={!showConfidence ? "active" : ""}
          onClick={() => setShowConfidence(false)}
        >
          Values
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={showConfidence}
          className={showConfidence ? "active" : ""}
          onClick={() => setShowConfidence(true)}
        >
          With Confidence
        </button>
      </div>
      <table className="imaging-summary-table">
        <thead>
          <tr>
            <th scope="col">Page #</th>
            <th scope="col">File</th>
            <th scope="col">Member Name</th>
            <th scope="col">Member DOB</th>
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
          {pages.map((p) => (
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

  if (tab === "doc") {
    return (
      <div className="imaging-panel-stack">
        <ManifestDetails
          manifest={manifest}
          verification={document.verification}
        />
        <DocSummary pages={document.pages} />
      </div>
    );
  }

  if (!currentPage) {
    return (
      <div className="imaging-panel-stack">
        <ManifestDetails
          manifest={manifest}
          verification={document.verification}
        />
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
      <ManifestDetails
        manifest={manifest}
        verification={document.verification}
      />
      <PageDetails page={currentPage} />
    </div>
  );
}

export type { ImagingTab };
