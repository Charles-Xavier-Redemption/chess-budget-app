import os
import psycopg2

# Load database URL from environment variable (set in Render & .env)
DATABASE_URL = os.environ.get("DATABASE_URL")

def test_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';")
        tables = cur.fetchall()
        print("Connected successfully! Public tables in this DB:")
        for t in tables:
            print("-", t[0])
        cur.close()
        conn.close()
    except Exception as e:
        print("Failed to connect to DB:", e)

if __name__ == "__main__":
    test_connection()
