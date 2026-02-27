import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus', user='postgres', password='himanshu')
cur = conn.cursor()

cur.execute("""
    ALTER TABLE responses
        ADD COLUMN IF NOT EXISTS grading_breakdown JSONB,
        ADD COLUMN IF NOT EXISTS manually_graded BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS override_note TEXT;
""")

conn.commit()

cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='responses' ORDER BY ordinal_position")
print("responses columns:", [r[0] for r in cur.fetchall()])
conn.close()
print("Migration complete.")
