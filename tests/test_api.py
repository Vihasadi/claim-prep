import sqlite3
from contextlib import closing
from dataclasses import replace

from fastapi.testclient import TestClient

from claim_prep.api import create_app
from conftest import ScriptedModel


def _client(settings, model=None):
    return TestClient(create_app(settings, model=model or ScriptedModel()))


def test_brief_end_to_end(settings):
    body = _client(settings).get("/api/deals/1/brief").json()
    assert body["deal"]["account"] == "Bracken Freight"
    assert body["brief"]["call_goal"].startswith("Get the CFO")
    assert body["playbook"]["scope"] == "deals vs Stackwise"
    assert [w["deal_id"] for w in body["similar_wins"]] == [2, 4]
    assert "metrics" in body["checklist"]["gaps"] and body["cached"] is False


def test_second_request_is_served_from_cache(settings):
    model = ScriptedModel()
    client = _client(settings, model)
    client.get("/api/deals/1/brief")
    second = client.get("/api/deals/1/brief").json()
    assert second["cached"] is True and len(model.calls) == 1


def test_refresh_and_new_activity_both_rebuild(settings):
    model = ScriptedModel()
    client = _client(settings, model)
    client.get("/api/deals/1/brief")
    client.get("/api/deals/1/brief?refresh=true")
    assert len(model.calls) == 2

    with closing(sqlite3.connect(settings.crm_db)) as conn, conn:
        conn.execute("INSERT INTO deal_activities (deal_id, kind, occurred_at, body) VALUES (1, 'call', '2026-11-01', 'x')")
    assert client.get("/api/deals/1/brief").json()["cached"] is False
    assert len(model.calls) == 3


def test_unknown_deal_is_404_and_bad_model_output_is_502(settings):
    assert _client(settings).get("/api/deals/999/brief").status_code == 404
    broken = _client(settings, ScriptedModel(lambda s, u: "I cannot help with that."))
    assert broken.get("/api/deals/1/brief").status_code == 502


def test_search_puts_open_deals_first(settings):
    results = _client(settings).get("/api/deals?q=platform").json()["results"]
    assert [r["id"] for r in results] == [1, 2]
    assert _client(settings).get("/api/deals?q=2").json()["results"][0]["account"] == "Hollis Ledger"


def test_api_key_is_enforced_when_configured(settings):
    client = _client(replace(settings, api_keys=("secret",)))
    assert client.get("/api/deals?q=b").status_code == 401
    assert client.get("/api/deals?q=b", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/deals?q=b", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/health").status_code == 200 and client.get("/").status_code == 200
