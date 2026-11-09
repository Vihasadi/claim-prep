"""Evidence from past wins: similar won deals (ClaimReplay) and the matching playbook (ClaimScout).

Both stores are optional. Without them a brief is still built, just from the
deal's own record. Both are plain SQLite files read here and only here.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from claim_prep.crm import Deal

STATUS_QUO = "status quo"   # how ClaimScout labels deals with no competing vendor


@dataclass(frozen=True)
class WinRef:
    deal_id: int
    account: str
    industry: str | None
    competitor: str | None
    turning_point: str
    winning_moves: tuple[str, ...]
    objections: tuple[tuple[str, str], ...]   # (objection, response that worked)

    def render(self) -> str:
        lines = [f"WON DEAL {self.deal_id}: {self.account} ({self.industry or '?'}, "
                 f"vs {self.competitor or STATUS_QUO})", f"Turning point: {self.turning_point}"]
        lines += [f"Move: {m}" for m in self.winning_moves[:4]]
        lines += [f'Objection: "{o}" -> {r}' for o, r in self.objections[:4]]
        return "\n".join(lines)


@dataclass(frozen=True)
class PlaybookRef:
    scope: str
    deal_count: int
    data: dict

    def render(self) -> str:
        d = self.data
        lines = [f"PLAYBOOK for {self.scope} (from {self.deal_count} won deals)", f"Headline: {d.get('headline', '')}"]
        lines += [f"Buyers tend to: {t}" for t in d.get("buyer_tendencies", [])]
        lines += [f"What works: {m}" for m in d.get("winning_moves", [])]
        lines += [f'Objection: "{o.get("objection")}" -> {o.get("best_response")}' for o in d.get("objections", [])]
        lines += [f"Watch out: {w}" for w in d.get("watch_outs", [])]
        return "\n".join(lines)


def _open(path: Path) -> sqlite3.Connection | None:
    if not Path(path).exists():
        return None
    return sqlite3.connect(f"{Path(path).resolve().as_uri()}?mode=ro", uri=True)


class Evidence:
    def __init__(self, replay_db: Path, playbook_db: Path):
        self._replay_db = replay_db
        self._playbook_db = playbook_db

    def similar_wins(self, deal: Deal, k: int = 3) -> list[WinRef]:
        """Won deals most like this one: same competitor counts most, then industry, then size."""
        conn = _open(self._replay_db)
        if conn is None:
            return []
        with closing(conn):
            rows = conn.execute(
                "SELECT deal_id, account, industry, competitor, amount, closed_at, replay_json FROM deal_replays"
            ).fetchall()
        scored = []
        for deal_id, account, industry, competitor, amount, closed_at, replay_json in rows:
            if deal_id == deal.id:
                continue
            score = 3 * ((competitor or None) == deal.competitor) + 2 * (industry == deal.industry)
            if amount and deal.amount and 0.5 <= amount / deal.amount <= 2:
                score += 1
            if score >= 2:
                scored.append((score, closed_at or "", deal_id, account, industry, competitor, replay_json))
        scored.sort(key=lambda r: (r[0], r[1]), reverse=True)
        return [self._win(*row[2:]) for row in scored[:k]]

    @staticmethod
    def _win(deal_id, account, industry, competitor, replay_json) -> WinRef:
        r = json.loads(replay_json)
        return WinRef(
            deal_id, account, industry, competitor or None, r.get("turning_point", ""),
            tuple(r.get("winning_moves", [])),
            tuple((o.get("objection", ""), o.get("response", "")) for o in r.get("objections", [])),
        )

    def playbook(self, deal: Deal) -> PlaybookRef | None:
        """The most specific playbook that exists: competitor + industry, then competitor, then industry."""
        conn = _open(self._playbook_db)
        if conn is None:
            return None
        rival = deal.competitor or STATUS_QUO
        lookups = [
            ("competitor_industry", rival, deal.industry, f"deals vs {rival} at {deal.industry} companies"),
            ("competitor", rival, None, f"deals vs {rival}"),
            ("industry", None, deal.industry, f"{deal.industry} deals"),
        ]
        with closing(conn):
            for kind, competitor, industry, scope in lookups:
                row = conn.execute(
                    "SELECT deal_count, playbook_json FROM segment_playbooks WHERE kind = ? "
                    "AND competitor IS ? AND industry IS ?", (kind, competitor, industry)).fetchone()
                if row:
                    return PlaybookRef(scope, row[0], json.loads(row[1]))
        return None

    def version(self) -> str:
        """Changes whenever either store is rewritten; part of the brief cache key."""
        stamps = []
        for path, sql in ((self._replay_db, "SELECT COUNT(*), MAX(created_at) FROM deal_replays"),
                          (self._playbook_db, "SELECT COUNT(*), MAX(generated_at) FROM segment_playbooks")):
            conn = _open(path)
            if conn is None:
                stamps.append("none")
                continue
            with closing(conn):
                stamps.append(str(conn.execute(sql).fetchone()))
        return "|".join(stamps)
