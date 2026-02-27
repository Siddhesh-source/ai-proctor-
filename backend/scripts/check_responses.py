import psycopg2
conn = psycopg2.connect(host='localhost', port=5432, dbname='morpheus', user='postgres', password='himanshu')
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='responses' ORDER BY ordinal_position")
print([r[0] for r in cur.fetchall()])
conn.close()
