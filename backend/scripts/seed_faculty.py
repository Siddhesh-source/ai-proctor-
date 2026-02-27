"""Seed or update a demo faculty account.

Run with: python scripts/seed_faculty.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

# Allow script to import from the app package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.db import User  # noqa: E402

DEMO_EMAIL = "faculty.demo@vit.edu"
DEMO_PASSWORD = "Faculty@12345"
DEMO_FULL_NAME = "Demo Faculty"
DEMO_ROLE = "professor"


async def seed_faculty() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == DEMO_EMAIL))
        user = result.scalar_one_or_none()
        password_hash = hash_password(DEMO_PASSWORD)

        if user:
            user.password_hash = password_hash
            user.role = DEMO_ROLE
            user.full_name = DEMO_FULL_NAME
            action = "updated existing"
        else:
            user = User(
                email=DEMO_EMAIL,
                password_hash=password_hash,
                role=DEMO_ROLE,
                full_name=DEMO_FULL_NAME,
            )
            session.add(user)
            action = "created new"

        await session.commit()
        print(f"✅ {action.capitalize()} faculty user: {DEMO_EMAIL}")


if __name__ == "__main__":
    asyncio.run(seed_faculty())
