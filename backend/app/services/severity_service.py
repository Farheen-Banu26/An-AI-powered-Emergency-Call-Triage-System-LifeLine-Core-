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
        "hostage": 5,
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
        "weapon": 4,
        "gun": 4,
        "knife": 4,
        "armed": 4,
        "threatening": 4,
        "robbery": 4,
        # Medium (3)
        "seizure": 3,
        "bleeding": 3,
        "broken bone": 3,
        "fracture": 3,
        "accident": 3,
        "assault": 3,
        "intruder": 3,
        "attack": 3,
        # Low (2)
        "blood": 2,
        "injury": 2,
        "cut": 2,
        "fall": 2,
        "pain": 2,

        # ── Multilingual Tamil Rules ──
        "மூச்சு விடவில்லை": 5,
        "மாரடைப்பு": 5,
        "மயக்கமடைந்து": 4,
        "மயக்கம்": 4,
        "தீ விபத்து": 4,
        "தீ": 4,
        "அதிக ரத்தம்": 4,
        "ரத்தம்": 3,
        "விபத்து": 3,
        "காயம்": 2,

        # ── Multilingual Hindi Rules ──
        "सांस नहीं ले रहे": 5,
        "सांस नहीं": 5,
        "दिल का दौरा": 5,
        "बेहोश": 4,
        "आग लग गई": 4,
        "आग": 4,
        "भारी खून": 4,
        "खून": 3,
        "दुर्घटना": 3,
        "चोट": 2,
    }

    def evaluate(self, transcript: str) -> Dict[str, Any]:
        """Calculate severity score from transcript text."""
        text_lower = transcript.lower()
        score = 0
        matched: list[str] = []
        matched_spans: list[tuple[int, int]] = []

        # Sort rules longest first to prevent sub-string double counting
        sorted_rules = sorted(self.RULES.items(), key=lambda x: len(x[0]), reverse=True)

        for keyword, weight in sorted_rules:
            start = 0
            while True:
                idx = text_lower.find(keyword, start)
                if idx == -1:
                    break
                end = idx + len(keyword)
                overlap = any(max(idx, s_idx) < min(end, e_idx) for s_idx, e_idx in matched_spans)
                if not overlap:
                    score += weight
                    matched.append(keyword)
                    matched_spans.append((idx, end))
                    break
                start = idx + 1

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
