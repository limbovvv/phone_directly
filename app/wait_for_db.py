import time
import sys
import psycopg2
import os

DSN = os.getenv('DATABASE_URL', 'postgresql://app:app@db:5432/phone_directly')
MAX_TRIES = 30
SLEEP = 2

for i in range(1, MAX_TRIES + 1):
    try:
        conn = psycopg2.connect(DSN)
        conn.close()
        print(f"DB is up on try {i}")
        sys.exit(0)
    except Exception as e:
        print(f"DB not ready (try {i}/{MAX_TRIES}): {e}")
        time.sleep(SLEEP)
print("DB connection failed after retries", file=sys.stderr)
sys.exit(1)
