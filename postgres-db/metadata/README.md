# Metadata CSVs → Manifest Details

## DATA_MODE behavior

| Mode | Manifest source |
|------|-----------------|
| `local` | Stacked files in this folder (`metadata_R{n}_B{n}.csv`) |
| `postgres` | `manifest_member_list` in Postgres (populated by db-insert) |

## File naming

```
metadata_R{n}_B{n}.csv
```

Examples: `metadata_R1_B1.csv`, `metadata_R2_B1.csv`

Multiple files are stacked (sorted by R, then B). Frontend local mode matches `recordId` → folder name.

## Columns

| Column | Description |
|--------|-------------|
| `recordId` | Chart / folder id |
| `DummyFirstName` | Member first name |
| `DummyLastName` | Member last name |
| `DummyDOB` | `MM/DD/YYYY` |
| `MemberID` | External member id |

## db-insert (writes to Postgres)

```bash
python load_from_folders.py --ddl
# stacks metadata_R*_B*.csv → INSERT manifest_member_list
```

Then set `DATA_MODE=postgres` so the UI reads Manifest Details from the DB.
