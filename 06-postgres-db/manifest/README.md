# Legacy pack manifest folder

Canonical Manifest CSVs now live in **`05-imaging-ui/data/metadata/`**.

This folder is kept only as a fallback for older checkouts. Prefer:

```bash
cp metadata_R*.csv ../05-imaging-ui/data/metadata/
cd ../db-insert-scripts
python load_pipeline.py
```
