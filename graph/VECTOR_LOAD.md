# Vector Embeddings Load Specification

This document details the exact procedure for generating and loading semantic vector embeddings into the TigerGraph `FraudInvestigation` graph for kNN vector search over historical closed cases (`ClosedCase` vertex type).

## 1. Overview & Dataset

- **Source File**: `data/closed_cases_history.csv` (5,565 historical closed fraud cases).
- **Target Vertex**: `ClosedCase` (primary_id: `case_id`, e.g. `CC-0001` through `CC-5565`).
- **Target Attributes**:
  - `note_text` (`STRING`): Raw human analyst notes from `analyst_notes` column (truncated to 500 characters).
  - `note_embedding` (`LIST<FLOAT>`): 384-dimensional dense embedding vector.

## 2. Embedding Model Specification

- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Embedding Dimension**: 384
- **Normalization**: `normalize_embeddings=True` (unit L2 norm for standard cosine similarity / dot product).
- **Device**: CPU / CUDA (CPU runtime: ~15 seconds for all 5,565 texts).

## 3. Reproduction Command

Run the loader script:

```bash
python scripts/load_vector_embeddings.py
```

### In-Code Execution Details:
1. Loads `data/closed_cases_history.csv`.
2. Extracts `analyst_notes` strings (handling NaN/empty as empty string).
3. Encodes using:
   ```python
   model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
   embeddings = model.encode(notes, batch_size=128, show_progress_bar=True, normalize_embeddings=True)
   ```
4. Authenticates to TigerGraph REST++ API using credentials from `.env` via `mcp.fallback_rest.TGConfig`.
5. Batches upserts in chunks of 500 via `POST /graph/{graph}`:
   ```json
   {
     "vertices": {
       "ClosedCase": {
         "<case_id>": {
           "note_text": {"value": "<note_text>"},
           "note_embedding": {"value": [0.012345, ...]}
         }
       }
     }
   }
   ```

## 4. Acceptance Result

- **Total Rows Processed**: 5,565
- **Total Vertices Accepted**: 5,565 / 5,565 (100% acceptance rate)
- **Zero Rejections / Errors**: Confirmed via REST++ batch response payloads.

## 5. Live Query Verification

Installed query: `graph/queries/vector_similar_cases.gsql`
```gsql
CREATE OR REPLACE QUERY vector_similar_cases(LIST<FLOAT> query_vector, INT k)
FOR GRAPH FraudInvestigation SYNTAX v2 {
  Res = vectorSearch({ClosedCase.note_embedding}, query_vector, k);
  PRINT Res[Res.case_id, Res.note_text, Res.outcome] AS similar_cases;
}
```

Verified live via:
```python
from mcp.fallback_rest import get_client
from agent.vector_memory import recall_similar_cases

client = get_client()
res = recall_similar_cases(client, query_text="card_not_present_fraud: high-risk transaction flagged", k=3)
assert len(res) == 3
```
