"""Verify the Railway Redis supports the query engine (FT.*) and vectors.
Reads RAILWAY_REDIS_URL from env (never printed)."""
import os

import redis

r = redis.from_url(os.environ["RAILWAY_REDIS_URL"], socket_timeout=15)
print("ping:", r.ping())
info = r.info("server")
print("redis_version:", info.get("redis_version"))
try:
    r.execute_command("FT._LIST")
    print("FT commands: available")
except redis.ResponseError as e:
    print("FT commands: MISSING ->", e)
