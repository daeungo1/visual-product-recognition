"""Guide-fit gate: decide whether a reviewed guide may be used for a photo.

A model (outside this module) judges each candidate guide and must quote the
sentence that justifies "match". This module verifies the quote against the
guide text, so an unverifiable judgement can never select a guide. Without a
verified guide the result is an explicit non-success state: nothing is drawn.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MIN_QUOTE_CHARS = 8
FITS = ("match", "partial", "mismatch")
NO_GUIDE = "no_verified_guide"


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def quote_in_text(quote: str | None, text: str) -> bool:
    if not quote:
        return False
    needle = _squash(quote).strip("\"'“”‘’")
    return len(needle) >= MIN_QUOTE_CHARS and needle in _squash(text)


@dataclass(frozen=True)
class FitDecision:
    chosen: str | None
    status: str  # "ok" or NO_GUIDE
    rejected: dict[str, str] = field(default_factory=dict)


def decide(
    verdicts: list[Mapping[str, Any]], chosen: str | None, guides: Mapping[str, str]
) -> FitDecision:
    """`verdicts`: {guide_id, product_ok, task_ok, fit, quote}; `guides`: id -> text."""
    by_id = {str(v.get("guide_id")): v for v in verdicts if v.get("guide_id") in guides}
    rejected: dict[str, str] = {}
    for guide_id, text in guides.items():
        v = by_id.get(guide_id)
        if v is None:
            rejected[guide_id] = "no verdict"
        elif v.get("fit") != "match" or not (
            v.get("product_ok") is True and v.get("task_ok") is True
        ):
            rejected[guide_id] = "not a match"
        elif not quote_in_text(v.get("quote"), text):
            rejected[guide_id] = "quote not found in guide"
    accepted = [g for g in guides if g not in rejected]
    if chosen in accepted:
        return FitDecision(chosen, "ok", rejected)
    if len(accepted) == 1:
        return FitDecision(accepted[0], "ok", rejected)
    return FitDecision(None, NO_GUIDE, rejected)
