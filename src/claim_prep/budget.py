"""Token estimates, and fitting text into a prompt budget.

The estimate is deliberately simple and provider-neutral: about 3.5
characters per token for English business prose, rounded up. It is
conservative for most tokenizers, and `LLMConfig.prompt_budget` keeps
another 10% in reserve. Because the estimate is a pure function of length,
clipping can compute the exact cut in one step instead of measuring and
retrying.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

CHARS_PER_TOKEN = 3.5
CUT_MARK = "\n[... trimmed to fit ...]\n"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def clip(text: str, max_tokens: int, *, head_share: float = 0.65) -> str:
    """Shorten `text` to `max_tokens` by cutting out its middle.

    Both ends of a section usually carry its point, so both are kept:
    `head_share` of the room goes to the start, the rest to the end.
    """
    if estimate_tokens(text) <= max_tokens:
        return text
    room = int(max_tokens * CHARS_PER_TOKEN) - len(CUT_MARK)
    if room <= 0:
        return CUT_MARK.strip()
    head = int(room * head_share)
    tail = room - head
    return text[:head] + CUT_MARK + (text[-tail:] if tail else "")


def newest_that_fit(blocks: Sequence[str], max_tokens: int, *, separator: str = "\n\n") -> tuple[str, int]:
    """The most recent blocks that fit in `max_tokens` together, returned in date order.

    `blocks` are oldest first. Before a call, last week's email matters more
    than how the deal opened, so the oldest blocks are the ones left out.
    Returns the joined text and how many older blocks were omitted.
    """
    kept: list[str] = []
    used = 0
    for block in reversed(blocks):
        cost = estimate_tokens(block + separator)
        if used + cost > max_tokens:
            if not kept:  # the newest block alone is too big: a clipped copy beats nothing
                kept.append(clip(block, max_tokens))
            break
        kept.append(block)
        used += cost
    kept.reverse()
    return separator.join(kept), len(blocks) - len(kept)
