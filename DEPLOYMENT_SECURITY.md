# Security Guide for Recozik Web API

This document provides security guidelines and best practices for deploying the Recozik web API in production.

## Table of Contents

- [Quick Start - Secure Production Setup](#quick-start---secure-production-setup)
- [Authentication & Authorization](#authentication--authorization)
- [Rate Limiting](#rate-limiting)
- [CORS Configuration](#cors-configuration)
- [File Upload Security](#file-upload-security)
- [Quota Management](#quota-management)
- [Logging & Monitoring](#logging--monitoring)
- [Environment Variables](#environment-variables)
- [Security Headers](#security-headers)
- [WebSocket Security](#websocket-security)

---

## Quick Start - Secure Production Setup

### 1. Generate Secure Admin Token

**CRITICAL**: Never use the default `dev-admin` token in production!

```bash
# Generate a secure random token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Example output: 8K7LN_9mPqRsT3vWxYz2AbCdEfGhIjKl4MnOpQrStUv
```

### 2. Configure Environment Variables

Create a `.env` file or set environment variables:

```bash
# REQUIRED for production
export RECOZIK_WEB_PRODUCTION_MODE=true
export RECOZIK_WEB_ADMIN_TOKEN="your-secure-token-here"

# Database paths
export RECOZIK_WEB_BASE_MEDIA_ROOT="/var/lib/recozik/media"
export RECOZIK_WEB_JOBS_DATABASE_URL="sqlite:////var/lib/recozik/jobs.db"
export RECOZIK_WEB_AUTH_DATABASE_URL="sqlite:////var/lib/recozik/auth.db"

# API keys
export RECOZIK_WEB_ACOUSTID_API_KEY="your-acoustid-key"
export RECOZIK_WEB_AUDD_TOKEN="your-audd-token"  # Optional

# Security settings
export RECOZIK_WEB_RATE_LIMIT_ENABLED=true
export RECOZIK_WEB_RATE_LIMIT_PER_MINUTE=60
export RECOZIK_WEB_RATE_LIMIT_TRUSTED_PROXIES=0  # Set to 1+ if behind proxy
export RECOZIK_WEB_MAX_UPLOAD_MB=32

# CORS (if serving a web frontend)
export RECOZIK_WEB_CORS_ENABLED=true
export RECOZIK_WEB_CORS_ORIGINS="https://your-frontend.com,https://app.yourdomain.com"
```

### 3. Verify Security Configuration

The application will **refuse to start** in production mode if the default admin token is detected:

```
SECURITY ERROR: Default admin token detected in production mode!
Set RECOZIK_WEB_ADMIN_TOKEN to a secure random value.
```

---

## Authentication & Authorization

### Token-Based Authentication

All API endpoints (except `/health`) require a valid API token in the `X-API-Token` header:

```bash
curl -H "X-API-Token: your-token-here" https://api.example.com/whoami
```

### Creating Additional Tokens

Use the admin token to create new tokens via the API:

```bash
curl -X POST https://api.example.com/admin/tokens \
  -H "X-API-Token: $RECOZIK_WEB_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "readonly-client",
    "display_name": "Read-Only Client",
    "roles": ["user"],
    "allowed_features": ["identify"],
    "quota_limits": {
      "acoustid_lookup": 1000,
      "audd_standard_lookup": 100
    }
  }'
```

> ℹ️ The creation response is the only time the server returns the full token.
> Subsequent calls to `/admin/tokens` expose only `token_hint`, so copy the value
> above immediately after creation.

### Token Roles

- **admin**: Full access to all endpoints including `/admin/*`
- **readonly**: Limited to identification endpoints with quotas
- **user**: Custom role with configurable permissions

---

## Rate Limiting

Rate limiting is **enabled by default** to prevent brute-force attacks and API abuse.

### Configuration

```bash
export RECOZIK_WEB_RATE_LIMIT_ENABLED=true
export RECOZIK_WEB_RATE_LIMIT_PER_MINUTE=60  # Max requests per minute per IP
export RECOZIK_WEB_RATE_LIMIT_TRUSTED_PROXIES=0  # Number of trusted proxies (default: 0)
```

### Trusted Proxies

If your application is behind a reverse proxy (nginx, traefik, etc.), set `RECOZIK_WEB_RATE_LIMIT_TRUSTED_PROXIES` to the number of proxies in your infrastructure:

- `0` (default): Don't trust X-Forwarded-For headers (most secure, direct connections only)
- `1`: Behind one proxy (e.g., nginx → app)
- `2`: Behind two proxies (e.g., cloudflare → nginx → app)

**SECURITY WARNING**: Only set this if you control the proxy infrastructure. An incorrect value allows attackers to bypass rate limiting by spoofing the X-Forwarded-For header.

### Behavior

- Authentication attempts are limited to 20/minute per IP by default
- Failed authentication attempts are logged with client IP
- HTTP 429 (Too Many Requests) returned when limit exceeded
- `Retry-After` header indicates when to retry
- Rate limits are applied per client IP address

### Monitoring Rate Limits

Check logs for rate limit violations:

```bash
grep "Rate limit exceeded" /var/log/recozik-web.log
```

---

## CORS Configuration

Configure Cross-Origin Resource Sharing if your API is accessed from web browsers.

### Enable CORS

```bash
export RECOZIK_WEB_CORS_ENABLED=true
export RECOZIK_WEB_CORS_ORIGINS="https://frontend.example.com,https://app.example.com"
```

### Multiple Origins

Provide comma-separated list of allowed origins:

```bash
# Comma-separated
export RECOZIK_WEB_CORS_ORIGINS="https://site1.com,https://site2.com"

# Or as JSON array (in config file)
cors_origins = ["https://site1.com", "https://site2.com"]
```

### Security Notes

- **Never** use `*` (wildcard) for production CORS origins
- Only specify HTTPS origins in production
- CORS is disabled by default for security

---

## File Upload Security

### Allowed Extensions

By default, only audio files are accepted:

```python
allowed_upload_extensions = [".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".opus", ".wma"]
```

### Custom Extensions

```bash
# Override allowed extensions (JSON array format)
export RECOZIK_WEB_ALLOWED_UPLOAD_EXTENSIONS='[".mp3", ".flac", ".wav"]'
```

### Upload Limits

```bash
export RECOZIK_WEB_MAX_UPLOAD_MB=32  # Maximum file size in MB
```

### Security Features

- ✅ Filename sanitization (directory traversal prevention)
- ✅ Extension validation (rejects non-audio files)
- ✅ Content-Type checking
- ✅ Size limits enforced
- ✅ Unique filenames (UUID-based)
- ✅ Temporary upload directory (configurable)

### Path Traversal Protection

The API includes **multiple layers** of protection against path traversal attacks:

1. Rejects absolute paths
2. Blocks `..` components
3. Validates normalized paths stay within media root
4. Uses `os.path` operations to prevent taint flow

---

## Quota Management

Quotas are **persistent** and survive server restarts (stored in SQLite).

### Quota Scopes

- `acoustid_lookup`: AcoustID API calls
- `audd_standard_lookup`: AudD standard API calls
- `audd_enterprise_lookup`: AudD enterprise API calls
- `musicbrainz_enrich`: MusicBrainz metadata enrichment

### Configuring Quotas

Set quotas when creating tokens:

```json
{
  "quota_limits": {
    "acoustid_lookup": 1000,
    "musicbrainz_enrich": 500
  }
}
```

### Rolling Windows

Quotas use a **24-hour rolling window** by default:

- Usage is tracked per hour
- Old records are automatically cleaned up
- Admin can reset quotas via API

### Monitoring Quotas

Quotas are logged when:

- ✅ Usage is recorded
- ⚠️ Limits are approached (80%+)
- ❌ Limits are exceeded

---

## Logging & Monitoring

### Log Levels

Configure logging verbosity:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Security Logs

The application generates security-relevant logs:

```
recozik.web.security - INFO - POST /identify/from-path from 192.168.1.100 - User-Agent: ...
recozik.web.auth - WARNING - Failed authentication attempt from IP 203.0.113.42 (token: abc12345...)
recozik.web.auth - INFO - Successful authentication for user 'john.doe' from IP 198.51.100.10
recozik.web.security - WARNING - Upload rejected: invalid extension '.exe'
recozik.web.quota - WARNING - Quota exceeded for user 'client1', scope acoustid_lookup: 1001 > 1000
```

### What to Monitor

1. **Failed authentication attempts** (potential attacks)
2. **Rate limit violations** (abuse detection)
3. **Quota exceedances** (usage patterns)
4. **Upload rejections** (malicious files)
5. **WebSocket connection failures**
6. **Path traversal attempts**

---

## Environment Variables Reference

```bash
# Production mode (REQUIRED for security)
RECOZIK_WEB_PRODUCTION_MODE=true

# Authentication
RECOZIK_WEB_ADMIN_TOKEN="secure-random-token"
RECOZIK_WEB_READONLY_TOKEN="readonly-token"  # Optional

# API Keys
RECOZIK_WEB_ACOUSTID_API_KEY="your-key"
RECOZIK_WEB_AUDD_TOKEN="your-token"  # Optional

# Paths
RECOZIK_WEB_BASE_MEDIA_ROOT="/var/lib/recozik/media"
RECOZIK_WEB_UPLOAD_SUBDIR="uploads"

# Security
RECOZIK_WEB_RATE_LIMIT_ENABLED=true
RECOZIK_WEB_RATE_LIMIT_PER_MINUTE=60
RECOZIK_WEB_RATE_LIMIT_TRUSTED_PROXIES=0
RECOZIK_WEB_MAX_UPLOAD_MB=32

# CORS
RECOZIK_WEB_CORS_ENABLED=false
RECOZIK_WEB_CORS_ORIGINS="https://frontend.example.com"

# Cache
RECOZIK_WEB_CACHE_ENABLED=true
RECOZIK_WEB_CACHE_TTL_HOURS=24
```

---

## Security Headers

The following security headers are **automatically added** to all responses:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```

In production mode with HTTPS:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

---

## WebSocket Security

### Authentication

WebSocket connections **require** the API token in the header:

```javascript
const ws = new WebSocket("wss://api.example.com/ws/jobs/abc123", {
  headers: {
    "X-API-Token": "your-token-here",
  },
});
```

### Security Notes

- ✅ Token must be in header (query parameters are **rejected**)
- ✅ Access control enforced (users can only access their own jobs)
- ✅ Admins can access all jobs
- ✅ Invalid tokens result in immediate connection closure

---

## Deployment Checklist

Before deploying to production:

- [ ] Set `RECOZIK_WEB_PRODUCTION_MODE=true`
- [ ] Generate and set secure `RECOZIK_WEB_ADMIN_TOKEN`
- [ ] Configure proper database paths
- [ ] Enable rate limiting
- [ ] Configure CORS if needed
- [ ] Set upload size limits
- [ ] Configure structured logging
- [ ] Set up log rotation
- [ ] Enable HTTPS (use reverse proxy like nginx/traefik)
- [ ] Configure firewall rules
- [ ] Set up monitoring/alerting
- [ ] Review and set appropriate quotas
- [ ] Test authentication and authorization
- [ ] Verify file upload restrictions
- [ ] Test rate limiting behavior

---

## Security Incident Response

### Suspected Token Compromise

1. Revoke the compromised token immediately
2. Generate a new token
3. Update client configurations
4. Review access logs for suspicious activity
5. Check quota usage for anomalies

### Rate Limit Attacks

1. Identify attacking IP addresses from logs
2. Consider adding IP-based blocking at firewall level
3. Reduce rate limits if necessary
4. Enable additional monitoring

### Suspicious File Uploads

1. Check security logs for rejected uploads
2. Review upload directory for unexpected files
3. Verify file extension validation is working
4. Consider additional content scanning if needed

---

**Last updated:** 2025-01-15
