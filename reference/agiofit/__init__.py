"""Agio Fit — reference implementation of the portable fit profile (v0.1 draft).

Deliberately small. If this file grows past a few hundred lines, the specification is doing too
little and the code is doing too much.
"""

from .match import (
    ExplanationLine,
    MatchReport,
    load_fit_profile,
    load_cut_profile,
    recommend,
)

__all__ = [
    "ExplanationLine",
    "MatchReport",
    "load_fit_profile",
    "load_cut_profile",
    "recommend",
]
__version__ = "0.1.0"
