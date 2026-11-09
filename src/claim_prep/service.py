"""The brief service: cache lookup, generation, and the response the API returns."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import defaultdict

from claim_prep import prompts
from claim_prep.briefing import Briefer, BriefInputs
from claim_prep.cache import BriefCache
from claim_prep.crm import CRM
from claim_prep.evidence import Evidence
from claim_prep.qualification import assess

logger = logging.getLogger(__name__)


class DealNotFound(LookupError):
    pass


class BriefFailed(RuntimeError):
    """The model could not produce a valid brief."""


class BriefService:
    def __init__(self, crm: CRM, evidence: Evidence, briefer: Briefer, cache: BriefCache, model_name: str):
        self._crm = crm
        self._evidence = evidence
        self._briefer = briefer
        self._cache = cache
        self._model_name = model_name
        # Two people opening the same deal at once should cost one generation, not two.
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def brief(self, deal_id: int, *, refresh: bool = False) -> dict:
        record = self._crm.load(deal_id)
        if record is None:
            raise DealNotFound(deal_id)
        wins = self._evidence.similar_wins(record.deal)
        playbook = self._evidence.playbook(record.deal)
        key = hashlib.sha256("|".join((record.fingerprint(), self._evidence.version(), prompts.PROMPT_VERSION,
                                       self._model_name)).encode()).hexdigest()[:20]

        async with self._locks[deal_id]:
            cached = None if refresh else self._cache.get(deal_id, key)
            if cached:
                brief, created_at = cached
            else:
                try:
                    brief = await self._briefer.build(BriefInputs(record, wins, playbook))
                except Exception as exc:
                    logger.warning("brief for deal %s failed: %s", deal_id, type(exc).__name__)
                    raise BriefFailed(str(deal_id)) from exc
                created_at = self._cache.put(deal_id, key, brief)

        d = record.deal
        checklist = assess(record.qualification)
        return {
            "deal": {"id": d.id, "name": d.name, "account": d.account, "industry": d.industry, "stage": d.stage,
                     "status": d.status, "amount": d.amount, "competitor": d.competitor},
            "brief": brief,
            "checklist": {"known": [e.key for e, _ in checklist.known], "gaps": [e.key for e in checklist.gaps]},
            "similar_wins": [{"deal_id": w.deal_id, "account": w.account, "turning_point": w.turning_point}
                             for w in wins],
            "playbook": {"scope": playbook.scope, "headline": playbook.data.get("headline")} if playbook else None,
            "generated_at": created_at,
            "cached": bool(cached),
        }

    def search(self, query: str) -> list[dict]:
        return self._crm.search(query)
