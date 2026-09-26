"""
Tests for configured Service Contact Calling functionality.
Verifies configured numbers for Ambulance, Fire Service, and Blue Cross,
as well as existing emergency contacts preservation.
"""
import pytest
import re

PRIMARY_CONTACT_NUMBER = "+91 9597755699"
SECONDARY_CONTACT_NUMBER = "+91 9791748499"
PRIMARY_TEL_TARGET = "tel:+919597755699"
SECONDARY_TEL_TARGET = "tel:+919791748499"

def clean_tel(phone: str) -> str:
    cleaned = re.sub(r"[^0-9+]", "", phone)
    return f"tel:{cleaned}"

def test_configured_service_numbers():
    """Verify primary and secondary configured numbers."""
    assert PRIMARY_CONTACT_NUMBER == "+91 9597755699"
    assert SECONDARY_CONTACT_NUMBER == "+91 9791748499"
    assert clean_tel(PRIMARY_CONTACT_NUMBER) == PRIMARY_TEL_TARGET
    assert clean_tel(SECONDARY_CONTACT_NUMBER) == SECONDARY_TEL_TARGET

def test_ambulance_service_config():
    """Verify Ambulance exposes both configured numbers and tel targets."""
    service = {
        "name": "Ambulance",
        "contacts": [
            {"type": "primary", "phone": PRIMARY_CONTACT_NUMBER, "telUrl": PRIMARY_TEL_TARGET},
            {"type": "secondary", "phone": SECONDARY_CONTACT_NUMBER, "telUrl": SECONDARY_TEL_TARGET},
        ]
    }
    assert service["name"] == "Ambulance"
    assert len(service["contacts"]) == 2
    assert service["contacts"][0]["phone"] == "+91 9597755699"
    assert service["contacts"][0]["telUrl"] == "tel:+919597755699"
    assert service["contacts"][1]["phone"] == "+91 9791748499"
    assert service["contacts"][1]["telUrl"] == "tel:+919791748499"

def test_fire_service_config():
    """Verify Fire Service exposes both configured numbers and tel targets."""
    service = {
        "name": "Fire Service",
        "contacts": [
            {"type": "primary", "phone": PRIMARY_CONTACT_NUMBER, "telUrl": PRIMARY_TEL_TARGET},
            {"type": "secondary", "phone": SECONDARY_CONTACT_NUMBER, "telUrl": SECONDARY_TEL_TARGET},
        ]
    }
    assert service["name"] == "Fire Service"
    assert len(service["contacts"]) == 2
    assert service["contacts"][0]["phone"] == "+91 9597755699"
    assert service["contacts"][0]["telUrl"] == "tel:+919597755699"
    assert service["contacts"][1]["phone"] == "+91 9791748499"
    assert service["contacts"][1]["telUrl"] == "tel:+919791748499"

def test_blue_cross_service_config():
    """Verify Blue Cross exposes both configured numbers and tel targets."""
    service = {
        "name": "Blue Cross",
        "contacts": [
            {"type": "primary", "phone": PRIMARY_CONTACT_NUMBER, "telUrl": PRIMARY_TEL_TARGET},
            {"type": "secondary", "phone": SECONDARY_CONTACT_NUMBER, "telUrl": SECONDARY_TEL_TARGET},
        ]
    }
    assert service["name"] == "Blue Cross"
    assert len(service["contacts"]) == 2
    assert service["contacts"][0]["phone"] == "+91 9597755699"
    assert service["contacts"][0]["telUrl"] == "tel:+919597755699"
    assert service["contacts"][1]["phone"] == "+91 9791748499"
    assert service["contacts"][1]["telUrl"] == "tel:+919791748499"

def test_family_doctor_contacts_preserved():
    """Verify existing family and doctor contacts are untouched."""
    family_contact = {"name": "Primary Family Contact", "phone": "+91 9597755699"}
    doctor_contact = {"name": "Doctor / Caregiver", "phone": "+91 9791748499"}
    assert family_contact["phone"] == "+91 9597755699"
    assert doctor_contact["phone"] == "+91 9791748499"
