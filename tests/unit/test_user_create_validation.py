import pytest
from pydantic import ValidationError

from app.schemas import UserCreate


def test_user_create_valid_company_email():
    u = UserCreate(
        email="personb@opsforge.ai",
        password="OpsForge@123",
        full_name="Person B",
    )
    assert u.email == "personb@opsforge.ai"


def test_user_create_rejects_gmail():
    with pytest.raises(ValidationError):
        UserCreate(
            email="someone@gmail.com",
            password="OpsForge@123",
            full_name="Someone",
        )


def test_user_create_weak_password():
    with pytest.raises(ValidationError):
        UserCreate(
            email="personc@opsforge.ai",
            password="password",
            full_name="Person C",
        )