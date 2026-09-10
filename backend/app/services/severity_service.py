from typing import Any, Dict


class SeverityService:
    """
    Deterministic rule-based severity scoring for emergency calls.
    Evaluates transcript text against keyword rules and returns a score + label.
    """

    RULES: dict[str, int] = {
        # Critical (5)
        "not breathing": 5,
        "can't breathe": 5,
        "cannot breathe": 5,
        "stopped breathing": 5,
        "heart attack": 5,
        "cardiac arrest": 5,
        "stroke": 5,
        "active shooter": 5,
        "bomb": 5,
        "explosion": 5,
        "building collapse": 5,
        # High (4)
        "difficulty breathing": 4,
        "unconscious": 4,
        "passed out": 4,
        "not awake": 4,
        "heavy bleeding": 4,
        "chest pain": 4,
        "trapped": 4,
        "drowning": 4,
        "fire": 4,
        "stabbed": 4,
        "shot": 4,
        # Medium (3)
        "seizure": 3,
        "bleeding": 3,
        "broken bone": 3,
        "fracture": 3,
        "accident": 3,
        "assault": 3,
        # Low (2)
        "blood": 2,
        "injury": 2,
        "cut": 2,
        "fall": 2,
        "pain": 2,
    }

    def evaluate(self, transcript: str) -> Dict[str, Any]:
        """Calculate severity score from transcript text."""
        text_lower = transcript.lower()
        score = 0
        matched: list[str] = []

        for keyword, weight in self.RULES.items():
            if keyword in text_lower:
                score += weight
                matched.append(keyword)

        if score >= 8:
            label = "CRITICAL (Cat 1)"
        elif score >= 5:
            label = "EMERGENCY (Cat 2)"
        elif score >= 3:
            label = "URGENT (Cat 3)"
        else:
            label = "ROUTINE (Cat 4)"

        return {
            "priority_score": score,
            "priority_label": label,
            "matched_keywords": matched,
        }
