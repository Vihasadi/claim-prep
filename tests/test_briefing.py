from claim_prep.briefing import MAX_QUESTIONS, Briefer, BriefInputs, finalize
from claim_prep.budget import newest_that_fit
from claim_prep.crm import CRM
from claim_prep.evidence import Evidence
from claim_prep.qualification import assess
from claim_prep.schema import Brief
from conftest import BRIEF


def test_assess_treats_placeholders_as_gaps():
    checklist = assess({"pain": "dashboards break", "metrics": "unknown", "champion": " TBD "})
    assert [e.key for e, _ in checklist.known] == ["pain"]
    assert {"metrics", "champion", "economic_buyer"} <= {e.key for e in checklist.gaps}


def test_every_gap_gets_a_question_and_bad_values_are_cleaned():
    checklist = assess({"pain": "x", "champion": "y", "competition": "z"})
    out = finalize(Brief.model_validate(BRIEF), checklist, shown_win_ids={2})

    covered = {c for q in out["questions"] for c in q["covers"]}
    assert {e.key for e in checklist.gaps} <= covered
    assert out["questions"][0]["covers"] == ["economic_buyer"]           # "bogus" key dropped
    assert any(q["source"] == "checklist" for q in out["questions"])
    assert [o["proof_deal_id"] for o in out["objections"]] == [2, None]   # 999 was never shown
    assert len(out["questions"]) <= MAX_QUESTIONS


def test_model_keeps_its_top_questions_even_with_many_gaps():
    many = dict(BRIEF, questions=[{"question": f"q{i}", "why": "w", "covers": []} for i in range(8)])
    out = finalize(Brief.model_validate(many), assess({}), shown_win_ids=set())
    model_qs = [q for q in out["questions"] if q["source"] == "model"]
    assert len(model_qs) == 3 and [q["question"] for q in model_qs] == ["q0", "q1", "q2"]
    assert len(out["questions"]) == 3 + 8  # all eight checklist gaps still covered


def test_newest_activities_are_kept_when_the_timeline_is_too_long():
    blocks = [f"activity {i} " + "x" * 100 for i in range(10)]
    text, omitted = newest_that_fit(blocks, 100)
    assert omitted > 0 and text.endswith(blocks[-1]) and blocks[0] not in text
    assert newest_that_fit(blocks, 10_000) == ("\n\n".join(blocks), 0)


def test_similar_wins_rank_competitor_over_industry(settings):
    crm, evidence = CRM(settings.crm_db), Evidence(settings.replay_db, settings.playbook_db)
    wins = evidence.similar_wins(crm.load(1).deal)
    # Deal 2: same competitor (+3) and similar size (+1); deal 4: same industry (+2) and size (+1); deal 3: neither.
    assert [w.deal_id for w in wins] == [2, 4]


def test_playbook_falls_back_from_specific_to_general(settings):
    deal = CRM(settings.crm_db).load(1).deal
    ref = Evidence(settings.replay_db, settings.playbook_db).playbook(deal)
    assert ref.scope == "deals vs Stackwise"   # no competitor+industry playbook exists


def test_missing_evidence_stores_are_fine(settings, tmp_path):
    evidence = Evidence(tmp_path / "none.sqlite3", tmp_path / "none2.sqlite3")
    deal = CRM(settings.crm_db).load(1).deal
    assert evidence.similar_wins(deal) == [] and evidence.playbook(deal) is None


def test_compose_includes_every_section(settings):
    record = CRM(settings.crm_db).load(1)
    evidence = Evidence(settings.replay_db, settings.playbook_db)
    message, _ = Briefer(None, 20_000).compose(BriefInputs(record, evidence.similar_wins(record.deal),
                                                           evidence.playbook(record.deal)))
    for expected in ("Bracken Freight", "Metrics: UNKNOWN", "Beat Stackwise", "WON DEAL 2", "quoted 20% less"):
        assert expected in message
