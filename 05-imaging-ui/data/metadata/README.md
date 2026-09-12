# Manifest metadata

Place stacked Manifest CSVs here:

```
metadata_R1_B1.csv
metadata_R2_B1.csv
…
```

Columns: `recordId,DummyFirstName,DummyLastName,DummyDOB,MemberID,…`

- **UI** (`DATA_MODE=local`): `METADATA_ROOT=./data/metadata`
- **Postgres load**: `python load_pipeline.py` → `manifest_member_list`
