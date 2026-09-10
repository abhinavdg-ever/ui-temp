# Member extraction & verification

Both page-level extraction and chart-level verification CSVs live here.

## Layout

```
02-imaging-pipeline/member-verification/
  output/member_extraction_results.csv
  output/member_verification_summary.csv
```

Per-chart optional overrides:

- `…/data/folders/<chart>/imaging/<chart>_member_extraction.csv`
- `…/data/folders/<chart>/imaging/<chart>_member_verification.csv`

---

## `member_extraction_results.csv` (page)

```csv
id,chart_id,page_name,extracted_name,extracted_dob,extracted_ssn,confidence,provided_name,provided_dob,provided_id,matched_id,created_at,updated_at
```

| Column | Imaging UI |
|--------|------------|
| `extracted_name` | Member Name |
| `extracted_dob` | Member DOB |
| `provided_id` / `matched_id` | Member ID (prefer matched, else provided) |
| `confidence` | Member confidence |

`chart_id` may be numeric (`52743839`); folders are often `52743839_44976074` — matching uses prefix.

---

## `member_verification_summary.csv` (doc)

```csv
id,chart_id,final_status,matched_member_info,matched_confidence,pages_matched,pages_checked,decision_reason
```

| Column | Imaging UI |
|--------|------------|
| `final_status` | Verification status (Accept / Reject) |
| `matched_confidence` | Doc-level match confidence |
| `decision_reason` | Reason text |
| `pages_matched` / `pages_checked` | Coverage |

Shown on the Imaging status strip when present.
