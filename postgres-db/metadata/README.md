# Metadata format (B1_R1_DummyMetadata)

Single CSV file — do **not** split per folder.

Columns (Excel sheet `B1_R1_DummyMetadata`):

| Column | Description |
|--------|-------------|
| `recordId` | Chart / folder id → `chart_list.chart_name` |
| `DummyFirstName` | Member first name |
| `DummyLastName` | Member last name |
| `DummyDOB` | Date of birth `MM/DD/YYYY` |
| `MemberID` | External member id → `manifest_member_list.external_member_id` |

## File

`postgres-db/metadata/B1_R1_DummyMetadata.csv`

Load with:

```bash
python load_from_folders.py --metadata-csv ../metadata/B1_R1_DummyMetadata.csv
```

(Default path is this file if `--metadata-csv` is omitted.)

## DB mapping

| CSV | `manifest_member_list` |
|-----|------------------------|
| `DummyFirstName` + `DummyLastName` | `member_name` (`First Last`) |
| `DummyDOB` | `member_dob` |
| `MemberID` | `external_member_id` |
| `recordId` | resolves `chart_id` via `chart_list.chart_name` |
