# Local Supabase Setup - Complete Guide

This guide explains how to run Supabase locally for faster development, configure environment variables, migrate your existing schema and data from Cloud Supabase, migrate storage files, and troubleshoot common issues on Windows.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Install Supabase CLI (Windows)](#install-supabase-cli-windows)
3. [Start Supabase Locally](#start-supabase-locally)
4. [Environment Variables](#environment-variables)
5. [Configure the App](#configure-the-app)
6. [Migrate Schema and Data](#migrate-schema-and-data)
7. [Migrate Storage Files](#migrate-storage-files)
8. [Switching Between Local and Cloud](#switching-between-local-and-cloud)
9. [Verify the Setup](#verify-the-setup)
10. [Useful Commands](#useful-commands)
11. [Troubleshooting (Windows)](#troubleshooting-windows)

---

## Prerequisites

### 1. Docker Desktop (Required)

- Download and install: https://www.docker.com/products/docker-desktop/
- Ensure Docker is running before starting Supabase

### 2. Supabase CLI

**Recommended (Windows - PowerShell):**

```powershell
# Install Scoop first
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Install Supabase CLI
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase

# Verify installation
supabase --version
```

**Alternative methods:**
- Chocolatey: `choco install supabase`
- Winget: `winget install Supabase.CLI`
- Direct binary: Download from https://github.com/supabase/cli/releases and add to PATH

### 3. PostgreSQL Client Tools (pg_dump, psql)

```powershell
# Install via Scoop
scoop install postgresql

# Or download official installer and add to PATH:
# C:\Program Files\PostgreSQL\<version>\bin
```

---

## Install Supabase CLI (Windows)

> ⚠️ **Note:** `npm install -g supabase` is NOT supported. Use one of these methods:

| Method | Command |
|--------|---------|
| **Scoop** (Recommended) | `scoop bucket add supabase https://github.com/supabase/scoop-bucket.git && scoop install supabase` |
| **Chocolatey** | `choco install supabase` |
| **Winget** | `winget install Supabase.CLI` |
| **Direct Download** | https://github.com/supabase/cli/releases |

---

## Start Supabase Locally

Run these commands in your project root:

```powershell
# Initialize Supabase (creates supabase/ folder)
supabase init

# Start local Supabase (first run pulls Docker images)
supabase start
```

When finished, you'll see output like:

```
Started supabase local development setup.

         API URL: http://127.0.0.1:54421
     GraphQL URL: http://127.0.0.1:54421/graphql/v1
  S3 Storage URL: http://127.0.0.1:54421/storage/v1/s3
    Database URL: postgresql://postgres:postgres@127.0.0.1:54422/postgres
      Studio URL: http://127.0.0.1:54423
     Mailpit URL: http://127.0.0.1:54424
 Publishable key: sb_publishable_XXXXXX
      Secret key: sb_secret_XXXXXX
```

**Save these values!** You'll need them for your `.env` file.

---

## Environment Variables

Update your `.env` file with both **Cloud** and **Local** credentials:

```env
# ============================================
# CLOUD SUPABASE (for migration script)
# ============================================
CLOUD_SUPABASE_URL=https://<project-ref>.supabase.co
CLOUD_SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIs...
CLOUD_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIs...
CLOUD_DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres

# ============================================
# LOCAL SUPABASE (for development)
# ============================================
SUPABASE_URL=http://127.0.0.1:54421
SUPABASE_SERVICE_ROLE_KEY=sb_secret_XXXXXX
SUPABASE_ANON_KEY=sb_publishable_XXXXXX
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54422/postgres

# ============================================
# OTHER APP CONFIG
# ============================================
OPENAI_API_KEY=your-openai-key
SECRET_KEY=your-secret-key
```

> **Note:** If your cloud password contains `@`, encode it as `%40` in the URL.

---

## Configure the App

The app reads environment variables automatically via `settings.py` and `supabase_config.py`. No code changes needed!

Just ensure your `.env` has the **local** values for `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, etc.

---

## Migrate Schema and Data

### Step 1: Ensure PostgreSQL Tools Work

```powershell
pg_dump --version
psql --version
```

If not found, add to PATH:
```powershell
$env:Path += ";C:\Program Files\PostgreSQL\18\bin"
```

### Step 2: Export Schema from Cloud

```powershell
pg_dump "postgresql://postgres:<PASSWORD>@db.<PROJECT>.supabase.co:5432/postgres" --schema-only --no-owner --no-acl -f schema_backup.sql
```

### Step 3: Export Data (Public Schema Only)

```powershell
pg_dump "postgresql://postgres:<PASSWORD>@db.<PROJECT>.supabase.co:5432/postgres" --data-only --schema=public --no-owner --no-acl -f public_data_backup.sql
```

### Step 4: Import to Local

```powershell
# Import schema (expect some errors for system schemas - that's OK!)
psql "postgresql://postgres:postgres@127.0.0.1:54422/postgres" -f schema_backup.sql

# Import your data
psql "postgresql://postgres:postgres@127.0.0.1:54422/postgres" -f public_data_backup.sql
```

> **Expected Errors:** You'll see errors like "schema 'auth' already exists" or "permission denied for schema storage". These are **normal** - local Supabase already has system schemas. Your `public` tables are what matters.

---

## Migrate Storage Files

We have a Python script to migrate storage buckets and files from Cloud to Local.

### Usage

```powershell
# Activate virtual environment
.\venv\Scripts\activate

# Run migration script
python scripts\migrate_storage.py --from-storage
```

### What It Does

1. **Lists cloud buckets** - Shows what's in your cloud storage
2. **Creates local buckets** - Creates matching buckets locally via REST API
3. **Downloads files** - Downloads each file from cloud storage
4. **Uploads to local** - Uploads to your local Supabase storage

### Available Options

| Flag | Description |
|------|-------------|
| `--list-only` | Only list cloud buckets and files (no migration) |
| `--from-storage` | Migrate all files found in cloud storage |
| (default) | Migrate only files referenced in database tables |

### Example Output

```
✓ Loaded environment from C:\...\AITeacherAssistant\.env
[*] Connecting to Cloud Supabase...
[*] Connecting to Local Supabase...

[*] Listing CLOUD storage buckets...
    Cloud buckets found: ['USER_UPLOADS', 'GENERATED_CONTENT']

[*] Ensuring local buckets...
    Existing local buckets: []
[*] Creating bucket 'USER_UPLOADS' via REST API...
[+] Created bucket: USER_UPLOADS
[*] Creating bucket 'GENERATED_CONTENT' via REST API...
[+] Created bucket: GENERATED_CONTENT

[*] Found 20 objects to migrate
[*] Migrating objects...
[>] Migrating GENERATED_CONTENT:university_.../Lecture_1.pdf
    [✓] Downloaded 6950 bytes from cloud
    [✓] Uploaded to local GENERATED_CONTENT
...

Summary: migrated=20, skipped=0, failed=0, total=20
[✓] Done.
```

### Manual Bucket Creation (If Script Fails)

If the script can't create buckets, create them manually:

1. Open **Local Studio**: http://127.0.0.1:54423
2. Go to **Storage** in the sidebar
3. Click **New bucket**
4. Create these buckets:
   - `LECTURE_MATERIALS`
   - `CURRICULUM_DOCS`
   - `GENERATED_CONTENT`
   - `USER_UPLOADS`
5. Set each to **Public** if needed

---

## Switching Between Local and Cloud

### Option 1: Separate .env Files

Create `.env.local` and `.env.cloud`, then copy the one you need:

```powershell
# Use local
copy .env.local .env

# Use cloud
copy .env.cloud .env
```

### Option 2: Comment/Uncomment in .env

```env
# LOCAL (active)
SUPABASE_URL=http://127.0.0.1:54421
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...

# CLOUD (commented out)
# SUPABASE_URL=https://project.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
```

---

## Verify the Setup

1. **Open Local Studio**: http://127.0.0.1:54423
2. **Check Tables**: Go to Table Editor → verify your tables exist
3. **Check Storage**: Go to Storage → verify buckets and files
4. **Run the App**:
   ```powershell
   python run.py
   ```
5. **Test Endpoints**: Hit API endpoints and confirm they work with local data

---

## Useful Commands

### Supabase CLI

```powershell
supabase start          # Start local Supabase
supabase stop           # Stop containers
supabase status         # Show running services
supabase logs           # View logs
supabase db reset       # Reset local DB (destructive!)
```

### PostgreSQL

```powershell
# Export schema
pg_dump "postgresql://..." --schema-only -f schema.sql

# Export data
pg_dump "postgresql://..." --data-only --schema=public -f data.sql

# Import
psql "postgresql://..." -f file.sql
```

### Storage Migration Script

```powershell
# List cloud storage contents
python scripts\migrate_storage.py --list-only

# Migrate all files from cloud storage
python scripts\migrate_storage.py --from-storage

# Migrate only DB-referenced files (default)
python scripts\migrate_storage.py
```

---

## Troubleshooting (Windows)

### 1. "npm install -g supabase" fails

Global npm install is not supported. Use **Scoop**, **Chocolatey**, or **Winget** instead.

### 2. "Ports are not available" on `supabase start`

Restart Windows NAT service:

```powershell
net stop winnat
net start winnat
```

Or change ports in `supabase/config.toml`:

```toml
[db]
port = 54432  # Changed from 54322

[api]
port = 54431  # Changed from 54321
```

### 3. `pg_dump` not recognized

Add PostgreSQL to PATH:

```powershell
$env:Path += ";C:\Program Files\PostgreSQL\18\bin"
```

Or add permanently via System → Environment Variables.

### 4. "syntax error at or near 'ÿ_'" when importing SQL

PowerShell's `>` creates UTF-16 files. Always use `-f` flag:

```powershell
# WRONG
pg_dump "..." > file.sql

# CORRECT
pg_dump "..." -f file.sql
```

### 5. Schema errors (auth, storage, etc.)

Errors like "schema 'auth' already exists" are **normal**. Local Supabase pre-creates system schemas. Your `public` schema tables are imported correctly.

### 6. Storage bucket creation fails

If the script shows "body/name must be string" errors:
1. Create buckets manually in Studio (http://127.0.0.1:54423 → Storage)
2. Or run `python scripts\migrate_storage.py --from-storage` which uses REST API

### 7. Analytics warning

"Analytics on Windows requires Docker daemon exposed on tcp://localhost:2375" - Safe to ignore for development.

---

## Security Notes

- Local keys (`sb_publishable_...`, `sb_secret_...`) are for **local development only**
- Never commit production secrets to git
- Use `.env` files locally, secret managers in production
- Keep `CLOUD_*` variables for migration scripts only

---

## Quick Reference

| What | Local | Cloud |
|------|-------|-------|
| **API URL** | `http://127.0.0.1:54421` | `https://<project>.supabase.co` |
| **DB URL** | `postgresql://postgres:postgres@127.0.0.1:54422/postgres` | `postgresql://postgres:<pwd>@db.<project>.supabase.co:5432/postgres` |
| **Studio** | http://127.0.0.1:54423 | https://supabase.com/dashboard |
| **Anon Key** | `sb_publishable_...` | `eyJhbGci...` (JWT) |
| **Service Key** | `sb_secret_...` | `eyJhbGci...` (JWT) |

---

*Last updated: December 2025*

