# Semantic model (MiniLM, all-MiniLM-L6-v2)

The accuracy report's semantic page-type match reads only these two files:
`tokenizer.json` and `onnx/model.onnx` (copied from the main repo's
`core-pipeline/models/semantic-model/`). Docker mounts this folder at
`/models/semantic-model`; a local run finds it next to `backend/`.
Without it the report still works, with the exact page-type match only.
