"""MEDDPICC: the qualification checklist the brief is organized around.

Each element is something a rep should know before forecasting a deal with
confidence. Which elements are still unknown is computed here, in code, from
the CRM, and every gap is guaranteed a discovery question in the brief (see
briefing.py), whatever the model decides to emphasize.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Element:
    key: str
    name: str
    meaning: str
    question: str   # a solid default discovery question, used when the model leaves the gap uncovered


FRAMEWORK: tuple[Element, ...] = (
    Element("metrics", "Metrics", "the measurable outcome the buyer expects",
            "A year from now, what would have to be measurably better for this to count as a success?"),
    Element("economic_buyer", "Economic buyer", "the person who can approve the spend",
            "Who signs off on a purchase like this, and what will they want to see before they do?"),
    Element("decision_criteria", "Decision criteria", "how the options will be compared",
            "How will you compare the options you're looking at, and what would rule one out?"),
    Element("decision_process", "Decision process", "the steps and people between now and a decision",
            "Can you walk me through what happens between your team saying yes and a signed agreement?"),
    Element("paper_process", "Paper process", "security, legal and procurement steps",
            "Which reviews does a new vendor go through here (security, legal, procurement) and how long "
            "do they usually take?"),
    Element("pain", "Identified pain", "the problem and what it costs",
            "When bad data gets through today, what happens, and what did the last incident cost you?"),
    Element("champion", "Champion", "someone inside who will sell for us",
            "Besides you, who wants this solved badly enough to make the case internally?"),
    Element("competition", "Competition", "the alternatives, including doing nothing",
            "What else are you considering, including keeping things as they are?"),
)
KEYS = frozenset(e.key for e in FRAMEWORK)
_EMPTY = {"", "unknown", "tbd", "?", "n/a", "none yet"}


@dataclass(frozen=True)
class Assessment:
    known: tuple[tuple[Element, str], ...]
    gaps: tuple[Element, ...]

    def render(self) -> str:
        lines = ["QUALIFICATION (MEDDPICC)"]
        lines += [f"- {e.name}: {value}" for e, value in self.known]
        lines += [f"- {e.name}: UNKNOWN ({e.meaning})" for e in self.gaps]
        return "\n".join(lines)


def assess(qualification: dict[str, str]) -> Assessment:
    known, gaps = [], []
    for element in FRAMEWORK:
        value = (qualification.get(element.key) or "").strip()
        if value.lower() in _EMPTY:
            gaps.append(element)
        else:
            known.append((element, value))
    return Assessment(tuple(known), tuple(gaps))
