"""Script to create test user in the database."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from app.db.database import SessionLocal, engine, Base
from app.db.models import User, OnboardingStatus

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt directly."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_test_user():
    """Create the test user."""
    db = SessionLocal()

    try:
        # Check if user already exists
        existing_user = db.query(User).filter(User.email == "jpgomez@stayirrelevant.com").first()

        if existing_user:
            print(f"User already exists: {existing_user.email}")
            print(f"User ID: {existing_user.id}")
            return existing_user

        # Create new user
        user = User(
            email="jpgomez@stayirrelevant.com",
            hashed_password=hash_password("Nov2011*"),
            name="Juan Pablo Gomez",
            onboarding_status=OnboardingStatus.NOT_STARTED,
            is_active=True,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print("Test user created successfully!")
        print(f"Email: {user.email}")
        print(f"User ID: {user.id}")
        print(f"Onboarding Status: {user.onboarding_status}")

        return user

    finally:
        db.close()


if __name__ == "__main__":
    create_test_user()
