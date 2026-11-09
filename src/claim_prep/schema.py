"""What the model returns for a brief. Validated with pydantic, then checked in code (briefing.py)."""

from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field


def _cap(n: int):
    return AfterValidator(lambda items: items[:n])


class Question(BaseModel):
    question: str = Field(description="Exactly what to ask, in the rep's voice.")
    why: str = Field(description="What the answer tells us, in one short sentence.")
    covers: list[str] = Field(default_factory=list,
                              description="MEDDPICC keys this question helps fill, e.g. ['economic_buyer'].")


class ObjectionPrep(BaseModel):
    objection: str = Field(description="A pushback this buyer is likely to raise next.")
    response: str = Field(description="How to answer it, concretely.")
    proof_deal_id: int | None = Field(
        default=None, description="The WON DEAL id whose experience backs this response, if one does.")


class Brief(BaseModel):
    snapshot: str = Field(description="Where the deal stands, in three sentences or fewer.")
    call_goal: str = Field(description="The one thing this next call must achieve.")
    questions: Annotated[list[Question], _cap(8)] = Field(description="Most important first.")
    objections: Annotated[list[ObjectionPrep], _cap(5)] = Field(default_factory=list)
    talk_track: Annotated[list[str], _cap(5)] = Field(
        default_factory=list, description="Short points to make on the call, in order.")
    risks: Annotated[list[str], _cap(4)] = Field(default_factory=list)
