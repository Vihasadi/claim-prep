"""HTTP API and the web page.

    GET /api/deals?q=bracken           find a deal
    GET /api/deals/{id}/brief          the pre-call brief (cached until something changes)
    GET /api/deals/{id}/brief?refresh=true
    GET /health
    GET /                              the web page
"""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.resources import files

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from claim_prep.briefing import Briefer
from claim_prep.cache import BriefCache
from claim_prep.config import Settings
from claim_prep.crm import CRM
from claim_prep.evidence import Evidence
from claim_prep.llm import ChatModel, OpenAIChat
from claim_prep.service import BriefFailed, BriefService, DealNotFound


def _key_check(keys: tuple[str, ...]):
    async def check(x_api_key: str | None = Header(default=None)) -> None:
        if not keys:
            return
        # Compare against every key in constant time, so timing reveals nothing about a near miss.
        if not x_api_key or not any(hmac.compare_digest(x_api_key, k) for k in keys):
            raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header")
    return check


def create_app(settings: Settings, *, model: ChatModel | None = None) -> FastAPI:
    """Build the app. Tests pass a fake `model`; otherwise an OpenAI-compatible client is created."""
    own_client = model is None
    chat_model: ChatModel = model or OpenAIChat(settings.llm)
    service = BriefService(
        CRM(settings.crm_db),
        Evidence(settings.replay_db, settings.playbook_db),
        Briefer(chat_model, settings.llm.prompt_budget),
        BriefCache(settings.cache_db),
        settings.llm.model or "test",
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if own_client:
            await chat_model.aclose()

    app = FastAPI(title="ClaimPrep", version="0.1.0", lifespan=lifespan)
    api = APIRouter(prefix="/api", dependencies=[Depends(_key_check(settings.api_keys))])

    @api.get("/deals")
    def search(q: str = Query(min_length=1, max_length=100)) -> dict:
        return {"results": service.search(q)}

    @api.get("/deals/{deal_id}/brief")
    async def brief(deal_id: int, refresh: bool = False) -> dict:
        try:
            return await service.brief(deal_id, refresh=refresh)
        except DealNotFound:
            raise HTTPException(status_code=404, detail=f"No deal {deal_id}") from None
        except BriefFailed:
            raise HTTPException(status_code=502, detail="The model could not produce a brief; try again") from None

    app.include_router(api)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def page() -> str:
        return files("claim_prep").joinpath("static/index.html").read_text(encoding="utf-8")

    return app
