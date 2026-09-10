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
id,chart_id,page_num,extracted_name,extracted_dob,extracted_gender,confidence,provided_name,provided_dob,provided_member_id,matched_member_info,created_at,updated_at
```

### Match keys
| CSV | Matches |
|-----|---------|
| `chart_id` | Folder name exact (`52743839_44976074`) or numeric prefix (`52743839`) |
| `page_num` (also `page_number` / `page_name`) | Page `#N` / `N.jpg` / file stem |

### Value columns → UI
| Column | Imaging UI |
|--------|------------|
| `extracted_name` | Extracted Name (Page Details + Doc Summary) |
| `extracted_dob` | Extracted DOB |
| `provided_member_id` / `provided_id` / `matched_id` | Member ID |
| `confidence` | Member confidence |

Not used: `extracted_gender`, `provided_name`, `provided_dob`, `matched_member_info`, `id`, timestamps.

---

## `member_verification_summary.csv` (doc)

```csv
id,chart_id,final_status,matched_member_id,matched_name,confidence,pages_matched,pages_checked,decision_reason
```

| Column | Imaging UI |
|--------|------------|
| `final_status` | Doc Summary → Rejection Rules → Status |
| `matched_name` | Matched name |
| `confidence` (or `matched_confidence`) | Confidence |
| `pages_matched` / `pages_checked` | Pages (`n/m`) |
| `decision_reason` | Decision Reason |

Match on `chart_id` = folder name. Shown only under **Rejection Rules** (no overall strip).
