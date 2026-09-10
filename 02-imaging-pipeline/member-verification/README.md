# Member Verification

Matches DB / Excel export **`member_verification_summary`**.

```csv
id,chart_id,final_status,matched_member_info,matched_confidence,pages_matched,pages_checked,decision_reason
```

| Column | Imaging UI |
|--------|------------|
| `final_status` | Verification status (Accept / Reject) |
| `matched_confidence` | Doc-level match confidence |
| `decision_reason` | Reason text |
| `pages_matched` / `pages_checked` | Coverage |

## Layout

```
02-imaging-pipeline/member-verification/
  output/member_verification_summary.csv
```

Shown on Imaging **Doc Summary** / manifest strip when present.
