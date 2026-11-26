# Semantic search for the "Suzirya" knowledge base

This project implements a local semantic search for a knowledge base with:

- document splitting into fragments,
- sentence-transformers embedding generation,
- cosine similarity search with a persisted index,
- BM25 keyword search on the same fragments,
- FastAPI web interface with filters and comparison tools.

## Project structure

- `docs/` — knowledge base documents with YAML metadata.
- `scripts/` — index build and environment check scripts.
- `app/` — business logic layered by responsibility.
- `templates/` — HTML interface.
- `compare/` — query set and evaluation script.

## Quick start

1. Install dependencies:
   `pip install -r requirements.txt`
2. Check the environment:
   `python scripts/check_environment.py`
3. Build the vector index:
   `python scripts/build_index.py`
4. Run the app:
   `uvicorn main:app --host 0.0.0.0 --port 8000`
5. Open http://localhost:8000

The app loads the index on start and displays a clear message if the index is missing.
