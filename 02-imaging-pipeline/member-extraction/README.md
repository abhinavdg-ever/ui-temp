# Member Extraction

Matches DB / Excel export **`member_extraction_results`**.

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

## Layout

```
02-imaging-pipeline/member-extraction/
  output/member_extraction_results.csv
```

Per chart optional:

`…/data/folders/<chart>/imaging/<chart>_member_extraction.csv`
