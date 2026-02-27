import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus', user='postgres', password='himanshu')
cur = conn.cursor()
cur.execute("""
    ALTER TABLE questions
    ADD COLUMN IF NOT EXISTS code_language VARCHAR(50),
    ADD COLUMN IF NOT EXISTS test_cases JSONB;
""")
conn.commit()
print('Migration done: code_language + test_cases added to questions')
cur.close()
conn.close()
