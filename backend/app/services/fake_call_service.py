"""
Fake / Prank Call Detection Service.

Multi-signal approach that combines:
  1. Keyword / pattern matching (fast, deterministic)
  2. Behavioral analysis (conversation-level patterns)
  3. LLM-based analysis (deep, semantic — runs per turn)

Each signal produces a 0.0–1.0 score. They are combined into a final
`fake_probability` (0.0 = definitely real, 1.0 = definitely fake) and
a `fake_label` (GENUINE / SUSPICIOUS / LIKELY_FAKE).
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 1. Keyword / Pattern Rules ──────────────────────────────────

# Phrases that strongly indicate a prank
_PRANK_PHRASES: list[str] = [
    "just kidding",
    "jk",
    "it's a prank",
    "its a prank",
    "this is a prank",
    "i'm joking",
    "im joking",
    "not real",
    "fake call",
    "testing",
    "test call",
    "just testing",
    "prank call",
    "dare",
    "for fun",
    "for a dare",
    "lol",
    "haha",
    "just playing",
    "messing around",
    "fooling around",
    "mazaak",           # Hindi for joke
    "mazak",
    "majak",
    "bakwas",           # Hindi for nonsense
    "timepass",
    "time pass",
    "joke",
    "joking",
    "sike",
    "psych",
    "gotcha",
    "april fools",
    "never mind",
    "nevermind",
    "nothing happened",
    "nothing is happening",
    "no emergency",
    "there is no emergency",
    "false alarm",
]

# Phrases indicating genuine distress (counter-signal)
_DISTRESS_PHRASES: list[str] = [
    "help",
    "please help",
    "hurry",
    "dying",
    "bleeding",
    "can't breathe",
    "cannot breathe",
    "heart attack",
    "unconscious",
    "fire",
    "trapped",
    "shot",
    "stabbed",
    "drowning",
    "accident",
    "collapse",
    "seizure",
    "chest pain",
    "emergency",
    "ambulance",
    "hurry up",
    "come fast",
    "please come",
    "save",
    "bachao",           # Hindi for "save me"
    "madad",            # Hindi for "help"
]

# Impossible / absurd scenarios
_ABSURD_PATTERNS: list[str] = [
    r"alien",
    r"ufo",
    r"zombie",
    r"dinosaur",
    r"dragon",
    r"meteor",
    r"spaceship",
    r"godzilla",
    r"vampire",
    r"werewolf",
    r"robot\s*attack",
    r"nuclear\s*bomb",
    r"time\s*travel",
]


class FakeCallDetector:
    """
    Stateful fake-call detector that accumulates evidence across
    multiple conversation turns for a single session.
    """

    def __init__(self):
        self._history: list[str] = []
        self._prank_hits: int = 0
        self._distress_hits: int = 0
        self._absurd_hits: int = 0
        self._contradiction_count: int = 0
        self._prev_emergency_type: Optional[str] = None

    # ── Public API ──────────────────────────────────────────────

    def evaluate_turn(
        self,
        transcript: str,
        emergency_type: Optional[str] = None,
        location: Optional[str] = None,
        details: Optional[str] = None,
        turn_count: int = 0,
        llm_fake_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate the latest transcript turn.

        Returns:
            {
                "fake_probability": 0.0–1.0,
                "fake_label": "GENUINE" | "SUSPICIOUS" | "LIKELY_FAKE",
                "fake_signals": ["list of reasons"],
            }
        """
        self._history.append(transcript)
        text = transcript.lower().strip()
        signals: list[str] = []

        # ── Signal 1: Prank keywords ────────────────────────────
        keyword_score = self._check_keywords(text, signals)

        # ── Signal 2: Absurd scenario ───────────────────────────
        absurd_score = self._check_absurd(text, signals)

        # ── Signal 3: Behavioral patterns ───────────────────────
        behavior_score = self._check_behavior(
            text, emergency_type, location, details, turn_count, signals
        )

        # ── Signal 4: LLM-based score (if provided by the analyst node)
        llm_score = llm_fake_score if llm_fake_score is not None else 0.0

        # ── Combine signals ─────────────────────────────────────
        # Weighted average: keywords (0.30), absurd (0.20), behavior (0.25), LLM (0.25)
        raw = (
            keyword_score * 0.30
            + absurd_score * 0.20
            + behavior_score * 0.25
            + llm_score * 0.25
        )

        # Reduce score if genuine distress signals are present
        distress_score = self._check_distress(text)
        if distress_score > 0:
            raw = max(0.0, raw - distress_score * 0.5)
            if distress_score > 0.3:
                signals.append("Distress signals detected — reducing fake probability")

        fake_probability = round(min(1.0, max(0.0, raw)), 2)

        if fake_probability >= 0.7:
            fake_label = "LIKELY_FAKE"
        elif fake_probability >= 0.4:
            fake_label = "SUSPICIOUS"
        else:
            fake_label = "GENUINE"

        logger.info(
            "Fake call check: prob=%.2f label=%s signals=%s",
            fake_probability, fake_label, signals,
        )

        return {
            "fake_probability": fake_probability,
            "fake_label": fake_label,
            "fake_signals": signals,
        }

    # ── Private Checks ──────────────────────────────────────────

    def _check_keywords(self, text: str, signals: list[str]) -> float:
        """Check for prank-indicating phrases. Returns 0.0–1.0."""
        hits = 0
        for phrase in _PRANK_PHRASES:
            if phrase in text:
                hits += 1
                self._prank_hits += 1
        if hits:
            signals.append(f"Prank keywords detected ({hits} matches)")
        # Single match = 0.6, multiple = higher
        if hits == 0:
            return 0.0
        return min(1.0, 0.6 + (hits - 1) * 0.15)

    def _check_absurd(self, text: str, signals: list[str]) -> float:
        """Check for absurd/impossible scenarios. Returns 0.0–1.0."""
        for pattern in _ABSURD_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                self._absurd_hits += 1
                signals.append(f"Absurd scenario: matched '{pattern}'")
                return 0.8
        return 0.0

    def _check_behavior(
        self,
        text: str,
        emergency_type: Optional[str],
        location: Optional[str],
        details: Optional[str],
        turn_count: int,
        signals: list[str],
    ) -> float:
        """Behavioral analysis across the conversation. Returns 0.0–1.0."""
        score = 0.0

        # Contradiction: emergency type changed drastically between turns
        if emergency_type and self._prev_emergency_type:
            if emergency_type != self._prev_emergency_type:
                self._contradiction_count += 1
                signals.append(
                    f"Emergency type changed: {self._prev_emergency_type} → {emergency_type}"
                )
                score += 0.4
        self._prev_emergency_type = emergency_type

        # Multiple contradictions = very suspicious
        if self._contradiction_count >= 2:
            score += 0.3
            signals.append("Multiple contradictions across turns")

        # Laughter / mockery patterns in text
        laugh_patterns = [r"ha{2,}", r"lol+", r"lmao", r"rofl", r"😂", r"🤣"]
        for lp in laugh_patterns:
            if re.search(lp, text, re.IGNORECASE):
                score += 0.3
                signals.append("Laughter/mockery detected")
                break

        # Very vague across multiple turns (no location, no details after 3+ turns)
        if turn_count >= 3 and not location and not details:
            score += 0.2
            signals.append("No location or details after 3+ turns")

        # Accumulated prank keyword hits across session
        if self._prank_hits >= 3:
            score += 0.3
            signals.append(f"Repeated prank keywords across session ({self._prank_hits} total)")

        return min(1.0, score)

    def _check_distress(self, text: str) -> float:
        """Check for genuine distress indicators. Returns 0.0–1.0."""
        hits = sum(1 for phrase in _DISTRESS_PHRASES if phrase in text)
        if hits == 0:
            return 0.0
        return min(1.0, hits * 0.25)
