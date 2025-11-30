# Migration Notes

This document tracks known technical debt and migration considerations for the recozik-web authentication system.

## User ID Type Inconsistency

### Current State

There is a type inconsistency in how user identifiers are represented across different layers:

1. **Database Layer (`User` model in `auth_models.py`)**:
   - `User.id: int | None` - Integer primary key (auto-increment)
   - Standard SQLModel pattern for database identity

2. **Token Storage Layer (`TokenRecord` in `auth_store.py`)**:
   - `TokenRecord.user_id: int` - References `User.id`
   - Foreign key relationship to the User table

3. **Service Layer (`ServiceUser` in `recozik_services.security`)**:
   - `ServiceUser.user_id: str` - Uses username as string identifier
   - Designed for cross-platform compatibility

### Why This Exists

- **Database**: Uses integer IDs for efficient indexing and foreign key relationships
- **Service Layer**: Uses username strings for human-readable identifiers and compatibility with stateless token systems
- **Token Storage**: Bridges both worlds by storing the integer database ID

### Conversion Points

The conversion happens in these key locations:

1. **`auth.py:resolve_user_from_token()`** (lines 313-338):

   ```python
   # Look up the username from the User table
   auth_store = get_auth_store(settings.auth_database_url_resolved)
   user = auth_store.get_user_by_id(record.user_id)  # record.user_id is int
   # ...
   return ServiceUser(
       user_id=user.username,  # Convert to string username
       # ...
   )
   ```

2. **`auth_routes.py:_user_to_response()`** (lines 139-151):
   ```python
   return UserResponse(
       id=user.id,  # type: ignore[arg-type] - int | None to int
       # ...
   )
   ```

### Known Issues

1. **Type Ignore Comments**: Several `# type: ignore[arg-type]` comments indicate places where the type system knows there's a mismatch
2. **Null Safety**: `User.id` can be `None` before database insert, requiring runtime checks
3. **API Confusion**: REST endpoints use integer IDs (`/admin/users/{user_id}`), but ServiceUser uses string username

### Migration Path (Future)

If we need to unify these types in the future, consider:

1. **Option A**: Make `ServiceUser.user_id` accept `str | int` and update all service layer code
2. **Option B**: Introduce a separate `ServiceUser.username` field and keep `user_id` as int
3. **Option C**: Use UUIDs for `User.id` and convert `ServiceUser.user_id` to UUID strings

**Current Recommendation**: Keep as-is. The conversion overhead is minimal and the separation provides clear boundaries between layers.

### Related Files

- `/packages/recozik-web/src/recozik_web/auth_models.py` - User model
- `/packages/recozik-web/src/recozik_web/auth_store.py` - TokenRecord
- `/packages/recozik-web/src/recozik_web/auth.py` - Type conversion logic
- `/packages/recozik-web/src/recozik_web/auth_routes.py` - REST API endpoints
- `/packages/recozik-services/src/recozik_services/security.py` - ServiceUser definition
