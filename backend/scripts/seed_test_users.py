"""Seed test users (professors and students) into the database.

Run with: python scripts/seed_test_users.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.db import User  # noqa: E402

TEST_USERS = [
    # Professors
    {"email": "prof.sharma@vit.edu",    "password": "ProfSharma@123",   "full_name": "Dr. Anil Sharma",    "role": "professor"},
    {"email": "prof.gupta@vit.edu",     "password": "ProfGupta@123",    "full_name": "Dr. Priya Gupta",    "role": "professor"},
    # Students
    {"email": "student1@vit.edu",       "password": "Student1@123",     "full_name": "Rahul Verma",        "role": "student"},
    {"email": "student2@vit.edu",       "password": "Student2@123",     "full_name": "Sneha Patel",        "role": "student"},
    {"email": "student3@vit.edu",       "password": "Student3@123",     "full_name": "Arjun Nair",         "role": "student"},
    {"email": "student4@vit.edu",       "password": "Student4@123",     "full_name": "Kavya Reddy",        "role": "student"},
    {"email": "student5@vit.edu",       "password": "Student5@123",     "full_name": "Rohan Deshmukh",     "role": "student"},
]


async def seed_users() -> None:
    async with AsyncSessionLocal() as session:
        for u in TEST_USERS:
            result = await session.execute(select(User).where(User.email == u["email"]))
            existing = result.scalar_one_or_none()
            pw_hash = hash_password(u["password"])

            if existing:
                existing.password_hash = pw_hash
                existing.role = u["role"]
                existing.full_name = u["full_name"]
                action = "Updated"
            else:
                session.add(User(
                    email=u["email"],
                    password_hash=pw_hash,
                    role=u["role"],
                    full_name=u["full_name"],
                ))
                action = "Created"

            print(f"  {action}: {u['email']} ({u['role']})")

        await session.commit()
        print(f"\nDone -- {len(TEST_USERS)} test users seeded.")


if __name__ == "__main__":
    asyncio.run(seed_users())
