# Support Assistant with structured output

This project implements a support assistant for an online store with:

- a FastAPI backend,
- structured JSON output with schema validation,
- conversation history trimming under a token budget,
- context engineering with rules loaded from `context.md`,
- comparison script for three prompt strategies,
- error handling for API failures and invalid responses.

## Run locally

1. Create a local `.env` file based on `.env.example`.
2. Install dependencies:
   `pip install -r requirements.txt`
3. Start the server:
   `uvicorn app.main:app --reload`
4. Open http://127.0.0.1:8000

## Important notes

- The real `.env` file must stay out of the repository.
- The assistant never invents policy facts. If policy is missing, it says that explicitly.
- The response object is validated before reaching the web layer.

## Files

- `app/` — backend and model integration
- `compare/` — strategy comparison and test cases
- `context.md` — business rules
- `requirements.txt` — Python dependencies
