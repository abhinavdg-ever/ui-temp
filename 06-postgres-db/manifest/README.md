# Manifest CSVs → Manifest Details

Put stacked `metadata_R{n}_B{n}.csv` files here (`06-postgres-db/manifest` on the laptop).

## DATA_MODE behavior

| Mode | Manifest source |
|------|-----------------|
| `local` | Stacked files in this folder (`metadata_R{n}_B{n}.csv`) |
| `postgres` | `manifest_member_list` in Postgres (populated by db-insert) |

## File naming

```
metadata_R{n}_B{n}.csv
```

Examples: `metadata_R1_B1.csv`, `Metadata_R1_B1.csv`

Multiple files are stacked (sorted by R, then B). Local mode matches `recordId` → folder / chart name.

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
python load_from_folders.py
# stacks manifest/metadata_R*_B*.csv → INSERT manifest_member_list
```
