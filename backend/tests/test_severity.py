"""Tests for the rule-based severity scoring service."""

import pytest
from app.services.severity_service import SeverityService


@pytest.fixture
def service():
    return SeverityService()


@pytest.mark.parametrize(
    "text, min_score, expected_label",
    [
        ("I can't breathe, please help", 5, "EMERGENCY (Cat 2)"),
        ("My husband is unconscious and bleeding", 7, "EMERGENCY (Cat 2)"),
        ("He passed out and is not breathing", 9, "CRITICAL (Cat 1)"),
        ("Somebody is having a heart attack", 5, "EMERGENCY (Cat 2)"),
        ("Just a routine check", 0, "ROUTINE (Cat 4)"),
    ],
)
def test_severity_scoring(service, text, min_score, expected_label):
    result = service.evaluate(text)
    assert result["priority_score"] >= min_score
    assert result["priority_label"] == expected_label


def test_empty_transcript(service):
    result = service.evaluate("")
    assert result["priority_score"] == 0
    assert result["priority_label"] == "ROUTINE (Cat 4)"
    assert result["matched_keywords"] == []
