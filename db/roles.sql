-- Dedicated read-only role. The db_query tool connects using THIS role,
-- not the main 'agent' superuser -- so even if application-level query
-- validation has a bug, the database itself has no write permission to
-- fall back on. This is the actual safety boundary; app-level SELECT-only
-- checking is a nice-to-have on top of it, not the other way around.

DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'agent_readonly') THEN
      CREATE ROLE agent_readonly WITH LOGIN PASSWORD 'readonly_dev_password';
   END IF;
END
$$;

GRANT CONNECT ON DATABASE agent_db TO agent_readonly;
GRANT USAGE ON SCHEMA public TO agent_readonly;
GRANT SELECT ON products TO agent_readonly;