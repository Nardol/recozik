# Database Migration Guide

This document describes database schema changes and migration procedures for the Recozik web backend.

## Overview

The Recozik web backend uses SQLite databases with SQLModel/SQLAlchemy ORM. Schema changes may require manual migration steps when upgrading.

**Database Files**:

- `auth.db` - User accounts, sessions, and API tokens (default location: `data/auth.db`)
- `jobs.db` - Background job tracking for file identification (default location: `data/jobs.db`)

**Schema Management**: SQLModel automatically creates tables via `SQLModel.metadata.create_all()` when the database is first initialized. However, schema changes to **existing** tables require manual migration.

---

## User Management Schema Changes (2025-01-30)

### Summary

Added comprehensive user management system with:

- New `User` table for user accounts
- Schema changes to `SessionToken` table (`user_id` changed from string to integer foreign key)
- New admin endpoints for user CRUD operations
- Password hashing with Argon2id
- Role-based access control (admin, operator, readonly)
- Per-user feature permissions and quota limits

### Breaking Changes

**⚠️ CRITICAL**: The `SessionToken.user_id` field changed from `str` to `int` (foreign key to `User.id`). This is a **breaking schema change** that requires migration.

### Migration Steps

#### Option 1: Fresh Start (Recommended for Development)

If you don't need to preserve existing sessions:

```bash
# Backup existing database
cp data/auth.db data/auth.db.backup

# Delete the database (will be recreated with new schema)
rm data/auth.db

# Restart the backend - it will create the new schema
cd packages/recozik-web
uv run uvicorn recozik_web.app:app --host 0.0.0.0 --port 8000
```

The backend will automatically:

1. Create the new `User` table
2. Create the updated `SessionToken` table with `user_id` as integer FK
3. Create the initial admin user from environment variables

**Initial Admin User**:
Set these environment variables before starting:

```bash
export RECOZIK_WEB_ADMIN_USERNAME="admin"
export RECOZIK_WEB_ADMIN_PASSWORD="your-secure-password-here"
export RECOZIK_WEB_ADMIN_EMAIL="admin@example.com"
```

#### Option 2: Manual Migration (Preserve Data)

If you need to preserve existing sessions, use this SQLite migration script:

```bash
# Backup first!
cp data/auth.db data/auth.db.backup

# Connect to the database
sqlite3 data/auth.db
```

Then run these SQL commands:

```sql
-- Create the new User table
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    roles TEXT DEFAULT '[]',  -- JSON array
    allowed_features TEXT DEFAULT '[]',  -- JSON array
    quota_limits TEXT DEFAULT '{}',  -- JSON object
    created_at TEXT NOT NULL
);

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_user_username ON user (username);
CREATE INDEX IF NOT EXISTS ix_user_email ON user (email);

-- Create a migration table for the old user_id values
CREATE TABLE sessiontoken_migration (
    old_user_id TEXT,
    new_user_id INTEGER
);

-- Insert unique user_id values from SessionToken
INSERT INTO sessiontoken_migration (old_user_id)
SELECT DISTINCT user_id FROM sessiontoken;

-- Create User records for each unique user_id
-- NOTE: You need to set proper passwords, emails, roles, and features
-- This creates placeholder users - update them afterward!
INSERT INTO user (username, email, password_hash, roles, allowed_features, created_at)
SELECT
    old_user_id,
    old_user_id || '@example.com',  -- Placeholder email
    '$argon2id$v=19$m=65536,t=3,p=4$placeholder',  -- INVALID - must be reset!
    '["readonly"]',
    '["identify"]',
    datetime('now')
FROM sessiontoken_migration;

-- Update the migration table with new user IDs
UPDATE sessiontoken_migration
SET new_user_id = (
    SELECT u.id FROM user u
    WHERE u.username = sessiontoken_migration.old_user_id
);

-- Create a new SessionToken table with the correct schema
CREATE TABLE sessiontoken_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    refresh_token TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    refresh_expires_at TEXT NOT NULL,
    remember INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES user (id)
);

CREATE INDEX ix_sessiontoken_new_session_id ON sessiontoken_new (session_id);
CREATE INDEX ix_sessiontoken_new_user_id ON sessiontoken_new (user_id);
CREATE INDEX ix_sessiontoken_new_refresh_token ON sessiontoken_new (refresh_token);

-- Migrate data to new table
INSERT INTO sessiontoken_new (
    session_id, user_id, refresh_token, created_at,
    expires_at, refresh_expires_at, remember
)
SELECT
    s.session_id,
    m.new_user_id,
    s.refresh_token,
    s.created_at,
    s.expires_at,
    s.refresh_expires_at,
    s.remember
FROM sessiontoken s
JOIN sessiontoken_migration m ON s.user_id = m.old_user_id;

-- Replace old table with new one
DROP TABLE sessiontoken;
ALTER TABLE sessiontoken_new RENAME TO sessiontoken;

-- Clean up
DROP TABLE sessiontoken_migration;

-- Verify migration
SELECT COUNT(*) FROM user;
SELECT COUNT(*) FROM sessiontoken;

.quit
```

**Post-Migration Steps**:

1. **Reset all user passwords** (the placeholder hash is invalid):

   ```bash
   # Use the admin API or recreate users with proper credentials
   # Example: Admin user
   export RECOZIK_WEB_ADMIN_USERNAME="admin"
   export RECOZIK_WEB_ADMIN_PASSWORD="SecurePassword123!"
   export RECOZIK_WEB_ADMIN_EMAIL="admin@example.com"

   # Start the backend and use /admin/users/{id}/reset-password endpoint
   ```

2. **Update user roles and features** via the admin dashboard or API

3. **Verify sessions** still work by logging in

### Schema Details

#### User Table

```python
class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    display_name: str | None = Field(default=None)
    password_hash: str  # Argon2id
    is_active: bool = Field(default=True)
    roles: list[str] = Field(default_factory=list)  # JSON: ["admin", "operator", "readonly"]
    allowed_features: list[str] = Field(default_factory=list)  # JSON: ["identify", "rename", ...]
    quota_limits: dict[str, int | None] = Field(default_factory=dict)  # JSON: {"acoustid_lookup": 100, ...}
    created_at: datetime
```

#### SessionToken Table (Updated)

```python
class SessionToken(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)
    user_id: int = Field(index=True, foreign_key="user.id")  # ← Changed from str
    refresh_token: str = Field(index=True, unique=True)
    created_at: datetime
    expires_at: datetime
    refresh_expires_at: datetime
    remember: bool = Field(default=False)
```

### New API Endpoints

**User Management** (admin only):

- `GET /admin/users` - List all users (pagination)
- `GET /admin/users/{id}` - Get user details
- `PUT /admin/users/{id}` - Update user
- `DELETE /admin/users/{id}` - Delete user
- `POST /admin/users/{id}/reset-password` - Admin password reset
- `GET /admin/users/{id}/sessions` - List user sessions
- `DELETE /admin/users/{id}/sessions` - Revoke all user sessions

**Authentication**:

- `POST /auth/register` - Create new user (admin only)
- Existing `/auth/login`, `/auth/logout`, `/auth/refresh`, `/whoami` work with new User model

### Password Requirements

All passwords must meet these criteria:

- Minimum 12 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one digit
- At least one symbol

### Environment Variables

New variables for initial admin setup:

```bash
# Required for first run
RECOZIK_WEB_ADMIN_USERNAME="admin"
RECOZIK_WEB_ADMIN_PASSWORD="YourSecurePassword123!"
RECOZIK_WEB_ADMIN_EMAIL="admin@example.com"

# Optional - customize admin user
RECOZIK_WEB_ADMIN_DISPLAY_NAME="System Administrator"
```

Existing auth database settings:

```bash
RECOZIK_WEB_AUTH_DATABASE_URL="sqlite:///data/auth.db"
```

### Testing the Migration

1. **Verify database schema**:

   ```bash
   sqlite3 data/auth.db ".schema user"
   sqlite3 data/auth.db ".schema sessiontoken"
   ```

2. **Check user count**:

   ```bash
   sqlite3 data/auth.db "SELECT COUNT(*) FROM user;"
   ```

3. **Test login**:

   ```bash
   curl -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"YourSecurePassword123!"}'
   ```

4. **Access admin endpoints**:
   ```bash
   # Get session cookies from login response
   curl -X GET http://localhost:8000/admin/users \
     -H "Cookie: recozik_session=..." \
     -H "X-CSRF-Token: ..."
   ```

### Rollback Procedure

If migration fails:

```bash
# Stop the backend
# Restore backup
cp data/auth.db.backup data/auth.db

# Checkout previous version
git checkout <previous-commit>

# Restart backend
```

---

## Future Migrations

For future schema changes:

1. **Always backup** `data/auth.db` and `data/jobs.db` before upgrading
2. **Check CHANGELOG.md** for breaking changes
3. **Review migration notes** in this file
4. **Test in development** environment first
5. **Use SQLite dump** for complex migrations:
   ```bash
   sqlite3 data/auth.db .dump > backup.sql
   ```

### Migration Best Practices

- Use transactions for multi-step migrations
- Create temporary tables for data transformation
- Verify foreign key integrity after schema changes
- Test with production-like data volumes
- Keep old backups for at least one release cycle

---

## Troubleshooting

### "FOREIGN KEY constraint failed"

The `SessionToken.user_id` must reference an existing `User.id`. Ensure all users are created before migrating sessions.

### "no such column: sessiontoken.user_id"

Old schema still in use. Run the migration script or delete and recreate the database.

### "Invalid password hash"

Placeholder hashes from migration are invalid. Reset passwords via:

```bash
curl -X POST http://localhost:8000/admin/users/1/reset-password \
  -H "Content-Type: application/json" \
  -H "Cookie: recozik_session=..." \
  -H "X-CSRF-Token: ..." \
  -d '{"new_password":"NewSecure123!"}'
```

### Sessions expired after migration

This is expected if you deleted the database. Users must log in again to create new sessions.

---

## Support

For issues with migrations:

1. Check the [GitHub Issues](https://github.com/Nardol/recozik/issues)
2. Review backend logs for SQLAlchemy errors
3. Verify SQLite database integrity: `sqlite3 data/auth.db "PRAGMA integrity_check;"`
