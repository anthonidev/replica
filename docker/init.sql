-- Crea la base de datos de backup si no existe.
-- La BD principal (clinicsay) ya la crea POSTGRES_DB en el compose.
SELECT 'CREATE DATABASE "clinicsay-backup" OWNER clinicsay'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'clinicsay-backup'
)\gexec
