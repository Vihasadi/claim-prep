"""Builds a brief: gather the inputs, fit them in the budget, ask the model, then check its work.

The prompt has five sections competing for one budget. The fixed ones
(deal header, checklist) are small. The evidence sections are each capped at
a share of the budget, and the activity timeline gets whatever is left,
filled from the newest activity backwards.

After the model answers, code enforces what a prompt alone can't promise:
- every qualification gap has at least one question (missing ones are added
  from the checklist and marked as such),
- `covers` only names real checklist keys,
- a `proof_deal_id` must be one of the won deals the model was shown.
"""

from __future__ import annotations

from dataclasses import dataclass

from claim_prep import prompts
from claim_prep.budget import clip, estimate_tokens, newest_that_fit
from claim_prep.crm import DealRecord
from claim_prep.evidence import PlaybookRef, WinRef
from claim_prep.llm import ChatModel
from claim_prep.qualification import KEYS, Assessment, assess
from claim_prep.schema import Brief
from claim_prep.structured import ask, prompt_tokens

MAX_QUESTIONS = 8
MIN_MODEL_QUESTIONS = 3
_SLACK = 120


@dataclass(frozen=True)
class BriefInputs:
    record: DealRecord
    wins: list[WinRef]
    playbook: PlaybookRef | None


class Briefer:
    def __init__(self, model: ChatModel, prompt_budget: int):
        self._model = model
        self._budget = prompt_budget

    def compose(self, inputs: BriefInputs) -> tuple[str, Assessment]:
        """The user message, fitted to the budget."""
        checklist = assess(inputs.record.qualification)
        room = self._budget - prompt_tokens(prompts.BRIEF_SYSTEM, Brief) - _SLACK

        header = clip(inputs.record.header(), room // 8)
        qualification = clip(checklist.render(), room // 8)
        playbook = clip(inputs.playbook.render(), room // 6) if inputs.playbook else "PLAYBOOK: none yet."
        wins = clip("\n\n".join(w.render() for w in inputs.wins), room // 4) if inputs.wins else "(none found)"

        left = room - sum(map(estimate_tokens, (header, qualification, playbook, wins)))
        timeline, omitted = newest_that_fit([a.render() for a in inputs.record.activities], max(left, 0))
        note = f"({omitted} older activities not shown)\n" if omitted else ""

        message = (f"{header}\n\n{qualification}\n\n{playbook}\n\nSIMILAR WON DEALS\n{wins}\n\n"
                   f"RECENT ACTIVITY (oldest first)\n{note}{timeline or '(no activity yet)'}")
        return message, checklist

    async def build(self, inputs: BriefInputs) -> dict:
        message, checklist = self.compose(inputs)
        brief = await ask(self._model, prompts.BRIEF_SYSTEM, message, Brief)
        return finalize(brief, checklist, {w.deal_id for w in inputs.wins})


def finalize(brief: Brief, checklist: Assessment, shown_win_ids: set[int]) -> dict:
    """Apply the code-side guarantees and return the brief as a plain dict for the API."""
    questions = [dict(q.model_dump(), covers=[c for c in q.covers if c in KEYS], source="model")
                 for q in brief.questions]

    def uncovered(qs: list[dict]) -> list:
        covered = {c for q in qs for c in q["covers"]}
        return [e for e in checklist.gaps if e.key not in covered]

    # Make room for the checklist questions, but always keep the model's top few.
    keep = max(MIN_MODEL_QUESTIONS, MAX_QUESTIONS - len(uncovered(questions)))
    questions = questions[:keep]
    questions += [{"question": e.question, "why": f"{e.name} is still unknown: {e.meaning}.",
                   "covers": [e.key], "source": "checklist"} for e in uncovered(questions)]

    objections = [dict(o.model_dump(), proof_deal_id=o.proof_deal_id if o.proof_deal_id in shown_win_ids else None)
                  for o in brief.objections]
    return {
        "snapshot": brief.snapshot,
        "call_goal": brief.call_goal,
        "questions": questions,
        "objections": objections,
        "talk_track": brief.talk_track,
        "risks": brief.risks,
    }
