-- One-time local dev database bootstrap (AGE container)
SELECT 'CREATE DATABASE advancedhadith'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'advancedhadith') \gexec
