-- =====================================================================
-- AI Imaging Pipeline — Abridged Schema
-- =====================================================================
-- Scoped-down subset of the full schema (schema.sql): the intake/imaging
-- core plus OCR and DOS extraction. No verification, decision, or
-- operational tables included.
--
-- Note: member_list is named manifest_member_list here for clarity (it
-- holds the parsed Manifest.xlsx candidates per chart). Let me know if
-- you want this renamed back to member_list to match the full schema —
-- right now the two files use different names for the same table.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Database name: imaging_outputs (host 172.20.4.170)
-- Tables live in schema public (as shown in DBeaver).
SET search_path TO public;

-- ---------------------------------------------------------------------
-- CORE
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS chart_list (
    id                  BIGSERIAL PRIMARY KEY,
    -- Not UNIQUE: loaders upsert by SELECT then UPDATE/INSERT.
    chart_name          VARCHAR(150) NOT NULL,
    page_count          INT,
    status              VARCHAR(30) NOT NULL DEFAULT 'received',
    blob_container_name VARCHAR(150),
    path                TEXT,                        -- path within the blob container
    run_id              VARCHAR(50),                  -- pipeline run this chart was processed under
    batch_id            VARCHAR(50),                  -- ingestion batch this chart belongs to
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chart_list_chart_name ON chart_list(chart_name);
CREATE INDEX IF NOT EXISTS idx_chart_list_status ON chart_list(status);
CREATE INDEX IF NOT EXISTS idx_chart_list_run_batch ON chart_list(run_id, batch_id);

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chart_list_updated_at ON chart_list;
CREATE TRIGGER trg_chart_list_updated_at
    BEFORE UPDATE ON chart_list
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS page_list (
    id                        BIGSERIAL PRIMARY KEY,
    chart_id                  BIGINT NOT NULL REFERENCES chart_list(id) ON DELETE CASCADE,
    page_name                 VARCHAR(150) NOT NULL,
    ocr_prelim_status         VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (ocr_prelim_status IN ('pending','processing','completed','failed')),
    ocr_final_status          VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (ocr_final_status IN ('pending','processing','completed','failed','skipped')),
    imaging_pipeline_status   VARCHAR(30) NOT NULL DEFAULT 'pending',
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chart_id, page_name)
);
CREATE INDEX IF NOT EXISTS idx_page_list_chart_id ON page_list(chart_id);

DROP TRIGGER IF EXISTS trg_page_list_updated_at ON page_list;
CREATE TRIGGER trg_page_list_updated_at
    BEFORE UPDATE ON page_list
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Chart-scoped candidate members (parsed Manifest.xlsx rows for this chart;
-- typically 2-3 candidates per chart)
CREATE TABLE IF NOT EXISTS manifest_member_list (
    id                  BIGSERIAL PRIMARY KEY,
    chart_id            BIGINT NOT NULL REFERENCES chart_list(id) ON DELETE CASCADE,
    member_name         VARCHAR(255) NOT NULL,
    member_dob          DATE,
    external_member_id  VARCHAR(100),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_manifest_member_list_chart_id ON manifest_member_list(chart_id);

DROP TRIGGER IF EXISTS trg_manifest_member_list_updated_at ON manifest_member_list;
CREATE TRIGGER trg_manifest_member_list_updated_at
    BEFORE UPDATE ON manifest_member_list
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------
-- OCR & DOS EXTRACTION
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ocr_results (
    id          BIGSERIAL PRIMARY KEY,
    chart_id    BIGINT NOT NULL REFERENCES chart_list(id) ON DELETE CASCADE,
    page_id     BIGINT NOT NULL REFERENCES page_list(id) ON DELETE CASCADE,
    -- prelim → tesseract | final1 → docling | final2 → azuredocintel
    ocr_type    VARCHAR(30) NOT NULL CHECK (ocr_type IN ('tesseract','docling','azuredocintel')),
    -- Store as-is: plain text (tesseract/docling) or JSON string (azuredocintel). Mix is OK.
    raw_text    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ocr_results_chart_id ON ocr_results(chart_id);
CREATE INDEX IF NOT EXISTS idx_ocr_results_page_id ON ocr_results(page_id);

DROP TRIGGER IF EXISTS trg_ocr_results_updated_at ON ocr_results;
CREATE TRIGGER trg_ocr_results_updated_at
    BEFORE UPDATE ON ocr_results
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Image / scan quality assessment
CREATE TABLE IF NOT EXISTS ocr_quality_results (
    id                BIGSERIAL PRIMARY KEY,
    chart_id          BIGINT NOT NULL REFERENCES chart_list(id) ON DELETE CASCADE,
    page_id           BIGINT NOT NULL REFERENCES page_list(id) ON DELETE CASCADE,
    quality_tag       VARCHAR(30),                    -- e.g. 'good','low_res','blurry','faxed'
    handwritten_flag  BOOLEAN NOT NULL DEFAULT FALSE,
    orientation       VARCHAR(20),                    -- e.g. 'portrait','landscape','rotated_90'
    mirror_angle      NUMERIC(6,2),
    tilt_angle        NUMERIC(6,2),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ocr_quality_chart_id ON ocr_quality_results(chart_id);
CREATE INDEX IF NOT EXISTS idx_ocr_quality_page_id ON ocr_quality_results(page_id);

DROP TRIGGER IF EXISTS trg_ocr_quality_updated_at ON ocr_quality_results;
CREATE TRIGGER trg_ocr_quality_updated_at
    BEFORE UPDATE ON ocr_quality_results
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS dos_extraction_results (
    id               BIGSERIAL PRIMARY KEY,
    chart_id         BIGINT NOT NULL REFERENCES chart_list(id) ON DELETE CASCADE,
    page_id          BIGINT NOT NULL REFERENCES page_list(id) ON DELETE CASCADE,
    -- Page-level extraction (NULL if this page had no explicit DOS)
    dos_from         DATE,
    dos_to           DATE,
    -- Document-level effective DOS (carry-forward / preamble default 2022-02-02)
    doc_dos_from     DATE,
    doc_dos_to       DATE,
    confidence       NUMERIC(5,4),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_dos_extraction_chart_id ON dos_extraction_results(chart_id);
CREATE INDEX IF NOT EXISTS idx_dos_extraction_page_id ON dos_extraction_results(page_id);

DROP TRIGGER IF EXISTS trg_dos_extraction_updated_at ON dos_extraction_results;
CREATE TRIGGER trg_dos_extraction_updated_at
    BEFORE UPDATE ON dos_extraction_results
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- =====================================================================
-- End of abridged schema
-- =====================================================================
