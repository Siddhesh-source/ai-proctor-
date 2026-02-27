"""Inspect demo faculty credentials."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.models.db import User  # noqa: E402

EMAIL = "faculty.demo@vit.edu"
PLAINTEXT = "Faculty@12345"


async def inspect() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == EMAIL))
        user = result.scalar_one_or_none()
        if not user:
            print("User not found")
            return
        print(f"Found user {user.email} role={user.role}")
        print(f"Password hash: {user.password_hash}")
        print("Verifying password...")
        print("Match?", verify_password(PLAINTEXT, user.password_hash))


if __name__ == "__main__":
    asyncio.run(inspect())
