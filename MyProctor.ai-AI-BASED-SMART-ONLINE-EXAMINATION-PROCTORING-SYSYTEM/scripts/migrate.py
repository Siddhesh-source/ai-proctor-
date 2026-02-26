"""
Database migration script
Creates all tables defined in the SQLAlchemy models
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.core.database import engine
from app.models.db import Base


async def create_tables():
    """Create all database tables"""
    print("Starting database migration...")
    print(f"Database URL: {engine.url}\n")
    
    try:
        # Try to create vector extension (optional)
        async with engine.begin() as conn:
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                print("✅ Vector extension enabled")
            except Exception as e:
                print(f"⚠️  Vector extension not available: {e}")
                print("   Continuing without vector support...\n")
        
        # Create all tables
        async with engine.begin() as conn:
            print("Creating tables...")
            await conn.run_sync(Base.metadata.create_all)
            print("✅ All tables created successfully!\n")
        
        # Verify tables were created
        async with engine.begin() as conn:
            result = await conn.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result.fetchall()]
            
            print(f"Created {len(tables)} tables:")
            for table in tables:
                print(f"   - {table}")
        
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


async def drop_tables():
    """Drop all database tables (use with caution!)"""
    print("⚠️  WARNING: This will delete all tables and data!")
    response = input("Are you sure you want to continue? (yes/no): ")
    
    if response.lower() != "yes":
        print("Operation cancelled.")
        return
    
    try:
        async with engine.begin() as conn:
            print("Dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
            print("✅ All tables dropped successfully!")
    except Exception as e:
        print(f"❌ Failed to drop tables: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Database migration tool")
    parser.add_argument(
        "action",
        choices=["create", "drop", "recreate"],
        help="Action to perform: create (create tables), drop (delete tables), recreate (drop and create)"
    )
    
    args = parser.parse_args()
    
    if args.action == "create":
        asyncio.run(create_tables())
    elif args.action == "drop":
        asyncio.run(drop_tables())
    elif args.action == "recreate":
        asyncio.run(drop_tables())
        asyncio.run(create_tables())
