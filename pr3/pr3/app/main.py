from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.config import settings
from app.llm import LLMService, LLMServiceError
from app.service import build_answer_payload, load_context

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="Support Assistant PR3")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class RequestBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, gt=0, le=2000)


class CompareRequest(BaseModel):
    messages: list[str] = Field(..., min_items=1, max_items=10)
    configurations: list[dict] = Field(..., min_items=1, max_items=10)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": settings.model_name,
        "base_url": settings.base_url,
    }


@app.post("/api/answer")
async def answer(payload: RequestBody) -> dict:
    llm = LLMService()
    context_text = load_context()
    request_data = build_answer_payload(
        payload.message,
        context_text,
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_tokens=payload.max_tokens,
    )
    try:
        result = await llm.generate(
            request_data["user_message"],
            request_data["context_text"],
            temperature=request_data["temperature"],
            top_p=request_data["top_p"],
            max_tokens=request_data["max_tokens"],
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {
        "answer": result["answer"],
        "model": result["model"],
        "elapsed_seconds": result["elapsed_seconds"],
        "attempts": result["attempts"],
    }


@app.post("/api/compare")
async def compare(payload: CompareRequest) -> dict:
    context_text = load_context()
    results = []
    for idx, message in enumerate(payload.messages):
        for cfg in payload.configurations:
            llm = LLMService()
            try:
                result = await llm.generate(
                    message,
                    context_text,
                    temperature=cfg.get("temperature", settings.temperature),
                    top_p=cfg.get("top_p", settings.top_p),
                    max_tokens=cfg.get("max_tokens", settings.max_tokens),
                )
                results.append(
                    {
                        "index": idx,
                        "configuration": cfg,
                        "answer": result["answer"],
                        "model": result["model"],
                        "elapsed_seconds": result["elapsed_seconds"],
                    }
                )
            except LLMServiceError as exc:
                results.append(
                    {
                        "index": idx,
                        "configuration": cfg,
                        "error": str(exc),
                        "status_code": exc.status_code,
                    }
                )
    return {"results": results}
