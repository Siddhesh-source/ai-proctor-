from collections.abc import AsyncGenerator
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


engine = create_async_engine(settings.DATABASE_URL, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
logger = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        table_result = await conn.execute(text("SELECT to_regclass('public.questions')"))
        has_questions = table_result.scalar() is not None
        logger.debug("DB init check", extra={"has_questions_table": has_questions})
        if has_questions:
            await conn.execute(
                text(
                    """
                    ALTER TABLE questions
                    ADD COLUMN IF NOT EXISTS code_language VARCHAR(50),
                    ADD COLUMN IF NOT EXISTS test_cases JSONB;
                    """
                )
            )
            logger.debug("Ensured coding columns exist on questions table")
    return None
