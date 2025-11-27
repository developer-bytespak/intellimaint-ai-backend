Prisma Workflow – Using db push for Schema Changes
Why we use db push

Prisma migrations (migrate dev) may fail due to:

Shadow DB issues.

Incorrect migration sequence.

Postgres extensions or type dependencies.

To avoid these issues, all schema changes are applied using db push only.

1️⃣ Updating the schema

Make changes in prisma/schema.prisma (e.g., add a field, change a type).

Ensure the datasource is defined as:

datasource db {
  provider   = "postgresql"
  url        = env("DATABASE_URL")
  extensions = [pgvector(map: "vector")]
}

2️⃣ Applying schema changes safely

Run:

npx prisma db push


Updates the database schema to match schema.prisma.

Preserves all existing data (do not use --force on production).

Creates any missing extensions if needed.

3️⃣ Update Prisma Client

After db push, regenerate the client:

npx prisma generate


Ensures your code can access new fields/tables in a type-safe way.

4️⃣ Tracking changes (optional, recommended)

Create a manual migration file for reference:

-- Example: migrations/<timestamp>_change_field_type/migration.sql
-- Record schema changes here for version control, e.g., new columns, altered types, or extensions.


Commit this folder to version control.

Do not execute it on DB; it’s only for tracking purposes.

5️⃣ Best Practices

Always backup the database before major schema changes.

Avoid editing old migration files.

Do not use migrate dev or shadow DB in production.

Small to medium schema changes → db push workflow.

For complex migrations requiring multiple environments → discuss before proceeding.
