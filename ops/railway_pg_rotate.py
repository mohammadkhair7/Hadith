"""Rotate the age-postgres role password. Reads RAILWAY_PG_URL (current) and
NEW_PG_PASSWORD from env; never prints either."""
import os
import sys

import psycopg
from psycopg import sql

url = os.environ["RAILWAY_PG_URL"]
new_pw = os.environ["NEW_PG_PASSWORD"]
if not new_pw or len(new_pw) < 20:
    sys.exit("NEW_PG_PASSWORD missing/too short")

with psycopg.connect(url, autocommit=True, connect_timeout=15) as conn:
    conn.execute(sql.SQL("ALTER USER ah PASSWORD {}").format(sql.Literal(new_pw)))
print("password rotated ok")
