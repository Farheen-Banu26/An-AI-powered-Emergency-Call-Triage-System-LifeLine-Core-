"""
Fake, Prank, and Test Call Detection Service.

Multi-tier approach combining:
  1. Explicit test & demo phrase detection (Deterministic, High Confidence)
  2. Prank, joke, mockery, and absurd scenario detection
  3. Behavioral conversation-level analysis (contradictions, vague stalling)
  4. Distress guardrails (Anti-False-Negative protection for real uncertain callers)
  5. LLM-assisted semantic scoring

Classifications:
  - GENUINE_EMERGENCY: Real distress or credible emergency reported
  - EXPLICIT_TEST: Caller explicitly stated they are testing, demoing, or no emergency exists
  - LIKELY_FAKE: Absurd scenarios, blatant mockery, or repeated prank indicators
  - SUSPICIOUS: Highly contradictory or questionable claims without distress
  - AMBIGUOUS: Vague statements requiring continued triage
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Explicit Test & Non-Emergency Statements ─────────────────────
_EXPLICIT_TEST_PATTERNS: list[str] = [
    r"\b(?:i\s*am|i'm|im|we\s*are|we're)\s+(?:only\s+|just\s+|simply\s+)?(?:testing|demoing|demonstrating|practicing|trying)\b",
    r"\b(?:this\s+is\s+|it's\s+|its\s+)?(?:only\s+|just\s+|simply\s+)?a\s+(?:test|demo|demonstration|trial|practice|drill)\b",
    r"\btesting\s+the\s+(?:system|app|application|service|lifeline)\b",
    r"\b(?:just\s+|only\s+)?testing\s+lifeline\b",
    r"\bthere\s+is\s+no\s+(?:real\s+|actual\s+|genuine\s+)?emergency\b",
    r"\bno\s+(?:real\s+|actual\s+|genuine\s+)?emergency\s*(?:here|at\s*all)?\b",
    r"\b(?:this\s+is\s+)?(?:not|isn't|is\s+not)\s+a\s+(?:real|genuine|actual)?\s*emergency\b",
    r"\bnot\s+(?:actually\s+|really\s+)?in\s+(?:danger|trouble|harm)\b",
    r"\b(?:i\s*am|i'm|im|we\s*are|we're)\s+not\s+(?:actually\s+|really\s+)?in\s+(?:danger|trouble)\b",
    r"\b(?:for\s+)?demonstration\s+(?:purposes?|only|mode|call)?\b",
    r"\bchecking\s+(?:whether|if)\s+(?:the\s+emergency\s+system|the\s+app|this|it)\s+works\b",
    r"\bsystem\s+test\b",
    r"\bjust\s+(?:trying|checking)\s+(?:out\s+)?(?:the\s+app|the\s+system|lifeline)\b",
    r"\b(?:don't|do\s*not)\s+send\s+(?:anyone|help|an?\s*ambulance|police|fire)\b",
    r"\bpractice\s+call\b",
    r"\bdoing\s+a\s+(?:demonstration|test|demo)\b",
    r"\bdemonstrating\s+the\s+(?:app|system|software)\b",
    r"\bparikshan\b",      # Hindi for testing
    r"\bsochanai\b",       # Tamil for testing
]

# ── Prank, Mockery & Slang Phrases ──────────────────────────────
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
    "prank call",
    "for a dare",
    "just playing",
    "messing around",
    "fooling around",
    "mazaak",           # Hindi for joke
    "mazak",
    "majak",
    "bakwas",           # Hindi for nonsense
    "timepass",
    "time pass",
    "sike",
    "psych",
    "gotcha",
    "april fools",
    "vilayattu",        # Tamil for playing / joke
]

# ── Impossible / Absurd Scenarios ───────────────────────────────
_ABSURD_PATTERNS: list[str] = [
    r"\balien(?:s)?\b",
    r"\bufo(?:s)?\b",
    r"\bzombie(?:s)?\b",
    r"\bdinosaur(?:s)?\b",
    r"\bdragon(?:s)?\b",
    r"\bmeteor\s*(?:strike|hit)?\b",
    r"\bspaceship\b",
    r"\bgodzilla\b",
    r"\bvampire(?:s)?\b",
    r"\bwerewolf\b",
    r"\brobot\s*attack\b",
    r"\btime\s*travel\b",
    r"\bintergalactic\b",
]

# ── Genuine Distress Counter-Signals (Safety Guardrails) ─────────
_DISTRESS_PHRASES: list[str] = [
    "help",
    "please help",
    "hurry",
    "dying",
    "bleeding",
    "blood",
    "can't breathe",
    "cannot breathe",
    "not breathing",
    "stopped breathing",
    "heart attack",
    "cardiac arrest",
    "unconscious",
    "not responding",
    "passed out",
    "collapsed",
    "fire",
    "smoke",
    "burning",
    "flames",
    "trapped",
    "shot",
    "gunshot",
    "stabbed",
    "knife",
    "drowning",
    "accident",
    "crash",
    "collision",
    "seizure",
    "stroke",
    "chest pain",
    "medical emergency",
    "life threatening",
    "ambulance",
    "hurry up",
    "come fast",
    "please come",
    "save",
    "bachao",           # Hindi for "save me"
    "madad",            # Hindi for "help"
    "kaapaatunga",      # Tamil for "save me"
    "maruthuva uthavi", # Tamil for "medical help"
    "theeyinaippu",     # Tamil for "fire service"
]


class FakeCallDetector:
    """
    Multi-signal Fake, Prank, and Test Call Detector.
    Ensures safe classification with zero false-negative tolerance for real emergencies.
    """

    def __init__(self):
        self._history: list[str] = []
        self._prank_hits: int = 0
        self._distress_hits: int = 0
        self._absurd_hits: int = 0
        self._contradiction_count: int = 0
        self._prev_emergency_type: Optional[str] = None

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
                "fake_probability": float (0.0 to 1.0),
                "fake_label": "GENUINE" | "EXPLICIT_TEST" | "LIKELY_FAKE" | "SUSPICIOUS" | "AMBIGUOUS",
                "is_test_call": bool,
                "fake_signals": list[str],
            }
        """
        self._history.append(transcript)
        text = transcript.lower().strip()
        signals: list[str] = []

        # ── Step 1: Check Explicit Test Patterns First ───────────
        is_explicit_test = False
        for pattern in _EXPLICIT_TEST_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                is_explicit_test = True
                signals.append(f"Explicit test statement: matched '{pattern}'")
                break

        # ── Step 2: Check Distress Guardrails (Safety First) ─────
        distress_score = self._check_distress(text)
        has_critical_distress = distress_score >= 0.25

        # If user explicitly states it's a test and NO critical distress keywords are present
        if is_explicit_test and not has_critical_distress:
            logger.info("Explicit test call detected [%s]", text[:60])
            return {
                "fake_probability": 1.0,
                "fake_label": "EXPLICIT_TEST",
                "is_test_call": True,
                "fake_signals": signals,
            }

        # ── Step 3: Check Prank Keywords & Absurd Scenarios ──────
        keyword_score = self._check_keywords(text, signals)
        absurd_score = self._check_absurd(text, signals)

        # ── Step 4: Check Behavioral Patterns ────────────────────
        behavior_score = self._check_behavior(
            text, emergency_type, location, details, turn_count, signals
        )

        # ── Step 5: LLM-based score ──────────────────────────────
        llm_score = float(llm_fake_score) if llm_fake_score is not None else 0.0

        # ── Step 6: Combine Signals ──────────────────────────────
        if absurd_score > 0.5:
            raw = max(0.85, absurd_score)
        elif keyword_score > 0.5:
            raw = max(0.75, keyword_score)
        else:
            raw = (
                keyword_score * 0.35
                + behavior_score * 0.35
                + llm_score * 0.30
            )

        # Apply distress mitigation: Real distress drastically reduces fake probability
        if distress_score > 0:
            raw = max(0.0, raw - distress_score * 0.75)
            signals.append("Distress signals detected — mitigating fake probability")

        fake_probability = round(min(1.0, max(0.0, raw)), 2)

        # Classify label
        if has_critical_distress:
            # Under critical distress, never label as fake
            fake_label = "GENUINE"
            fake_probability = min(fake_probability, 0.1)
        elif fake_probability >= 0.75:
            fake_label = "LIKELY_FAKE"
        elif fake_probability >= 0.45:
            fake_label = "SUSPICIOUS"
        elif any(term in text for term in ["not sure", "might be", "i think", "maybe", "confused"]) and not emergency_type:
            fake_label = "AMBIGUOUS"
        else:
            fake_label = "GENUINE"

        logger.info(
            "Fake call check: prob=%.2f label=%s signals=%s",
            fake_probability, fake_label, signals,
        )

        return {
            "fake_probability": fake_probability,
            "fake_label": fake_label,
            "is_test_call": is_explicit_test,
            "fake_signals": signals,
        }

    def _check_keywords(self, text: str, signals: list[str]) -> float:
        hits = sum(1 for phrase in _PRANK_PHRASES if phrase in text)
        if hits:
            self._prank_hits += hits
            signals.append(f"Prank keywords detected ({hits} matches)")
            return min(1.0, 0.7 + (hits - 1) * 0.15)
        return 0.0

    def _check_absurd(self, text: str, signals: list[str]) -> float:
        for pattern in _ABSURD_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                self._absurd_hits += 1
                signals.append(f"Absurd scenario: matched '{pattern}'")
                return 0.95
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
        score = 0.0

        if emergency_type and self._prev_emergency_type and emergency_type != self._prev_emergency_type:
            self._contradiction_count += 1
            signals.append(f"Emergency type changed: {self._prev_emergency_type} → {emergency_type}")
            score += 0.4
        self._prev_emergency_type = emergency_type

        laugh_patterns = [r"ha{2,}", r"lol+", r"lmao", r"rofl", r"😂", r"🤣"]
        for lp in laugh_patterns:
            if re.search(lp, text, re.IGNORECASE):
                score += 0.4
                signals.append("Laughter/mockery detected")
                break

        if turn_count >= 3 and not location and not details:
            score += 0.25
            signals.append("No location or details after 3+ turns")

        if self._prank_hits >= 2:
            score += 0.35
            signals.append(f"Repeated prank indicators ({self._prank_hits} total)")

        return min(1.0, score)

    def _check_distress(self, text: str) -> float:
        # Strip negative statements before checking distress phrases
        cleaned = re.sub(r"\b(?:no|not|never|without)\s+(?:emergency|danger|harm|injury|problem|threat|injuries)\b", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(?:just|system)\s+testing\b", "", cleaned, flags=re.IGNORECASE)
        hits = sum(1 for phrase in _DISTRESS_PHRASES if phrase in cleaned)
        if hits == 0:
            return 0.0
        return min(1.0, hits * 0.35)
