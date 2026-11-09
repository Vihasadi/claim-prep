"""Fixtures: a small CRM, ClaimReplay/ClaimScout stores, and a scripted model."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest

from claim_prep.config import LLMConfig, Settings

SCHEMA = (Path(__file__).parents[1] / "sql" / "crm_schema.sql").read_text(encoding="utf-8")

BRIEF = {
    "snapshot": "Security review is open; the CFO has not been involved yet.",
    "call_goal": "Get the CFO into next week's review.",
    "questions": [
        {"question": "Who signs off on this?", "why": "Find the buyer", "covers": ["economic_buyer", "bogus"]},
        {"question": "What does a bad-data incident cost?", "why": "Size the pain", "covers": ["pain"]},
    ],
    "objections": [
        {"objection": "Stackwise is cheaper", "response": "Show payback", "proof_deal_id": 2},
        {"objection": "Security", "response": "Send SOC 2", "proof_deal_id": 999},
    ],
    "talk_track": ["Recap the pain", "Propose a proof of concept"],
    "risks": ["No champion yet"],
}


class ScriptedModel:
    def __init__(self, respond: Callable[[str, str], str] | None = None):
        self.calls: list[tuple[str, str]] = []
        self._respond = respond or (lambda s, u: json.dumps(BRIEF))

    async def complete(self, system: str, user: str, *, json: bool = False) -> str:
        self.calls.append((system, user))
        return self._respond(system, user)


def build_crm(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.executescript(SCHEMA)
        conn.executescript("""
            INSERT INTO sales_deals (id, name, account_name, industry, employees, region, amount, stage, status,
                                     competitor, owner, meddpicc, created_at, closed_at, updated_at) VALUES
                (1, 'Bracken Freight - platform', 'Bracken Freight', 'Logistics', 900, 'EMEA', 60000, 'evaluation',
                 'open', 'Stackwise', 'Jordan Ellis',
                 '{"pain": "dashboards break weekly", "champion": "Priya Okafor", "competition": "Stackwise",
                   "metrics": "unknown"}',
                 '2026-09-01', NULL, '2026-10-20'),
                (2, 'Hollis Ledger - platform', 'Hollis Ledger', 'Fintech', 450, 'North America', 48000, 'closed_won',
                 'won', 'Stackwise', 'Sam Whitaker', '{}', '2026-01-10', '2026-04-02', '2026-04-02');
            INSERT INTO deal_contacts (deal_id, name, title, persona) VALUES
                (1, 'Priya Okafor', 'Head of Data', 'champion'), (1, 'Marcus Varga', 'CFO', 'economic_buyer');
            INSERT INTO deal_activities (deal_id, kind, occurred_at, subject, body) VALUES
                (1, 'call', '2026-09-02', 'Discovery', 'Priya described weekly dashboard breakages.'),
                (1, 'email', '2026-10-01', 'Security', 'Their CISO asked for a SOC 2 report.'),
                (1, 'note', '2026-10-20', 'Pricing', 'Priya says Stackwise quoted 20% less.');
        """)


def build_replays(path: Path) -> None:
    replay = {"turning_point": "POC caught issues Stackwise missed", "winning_moves": ["Two-week POC"],
              "objections": [{"objection": "Stackwise is cheaper", "response": "Payback case", "outcome": "resolved"}]}
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE deal_replays (deal_id INTEGER PRIMARY KEY, account TEXT, industry TEXT, competitor TEXT, "
                     "amount REAL, closed_at TEXT, replay_json TEXT, created_at TEXT)")
        conn.executemany("INSERT INTO deal_replays VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            (2, "Hollis Ledger", "Fintech", "Stackwise", 48000, "2026-04-02", json.dumps(replay), "2026-04-03"),
            (3, "Alder Goods", "Retail", "Corvane", 30000, "2026-05-01", json.dumps(replay), "2026-05-02"),
            (4, "Cinder Haulage", "Logistics", None, 55000, "2026-06-01", json.dumps(replay), "2026-06-02"),
        ])


def build_playbooks(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE segment_playbooks (id INTEGER PRIMARY KEY, kind TEXT, competitor TEXT, industry TEXT, "
                     "deal_count INTEGER, sample_size INTEGER, playbook_json TEXT, prompt_version TEXT, "
                     "generated_at TEXT)")
        conn.executemany(
            "INSERT INTO segment_playbooks (kind, competitor, industry, deal_count, sample_size, playbook_json, "
            "prompt_version, generated_at) VALUES (?, ?, ?, ?, ?, ?, 'v', '2026-11-01')", [
                ("competitor", "Stackwise", None, 9, 9, json.dumps({"headline": "Beat Stackwise on time to value."})),
                ("industry", None, "Logistics", 6, 6, json.dumps({"headline": "Logistics buyers test alerts."})),
            ])


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    build_crm(tmp_path / "crm.sqlite3")
    build_replays(tmp_path / "replays.sqlite3")
    build_playbooks(tmp_path / "playbooks.sqlite3")
    return Settings(crm_db=tmp_path / "crm.sqlite3", replay_db=tmp_path / "replays.sqlite3",
                    playbook_db=tmp_path / "playbooks.sqlite3", cache_db=tmp_path / "briefs.sqlite3",
                    llm=LLMConfig(model="test-model"))
