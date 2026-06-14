# Contract: Scraper Session API

**Base path**: `/api/scraper/yandex`

## POST /api/scraper/yandex/login

Start operator login using environment credentials (`YANDEX_OPERATOR_LOGIN`, `YANDEX_OPERATOR_PASSWORD`).
Runs Playwright login flow; saves storage state to configured path.

**Response 202**:

```json
{
  "status": "running | needs_manual_action | valid",
  "message": "string"
}
```

On captcha/2FA: `status: needs_manual_action` with guidance.

**Security**: Response MUST NOT include password, cookies, or storage state JSON.

## GET /api/scraper/yandex/session

Current session status.

**Response 200**:

```json
{
  "status": "missing | valid | expired | needs_manual_action",
  "last_login_at": "ISO8601 | null",
  "last_checked_at": "ISO8601 | null",
  "storage_state_path": "string"
}
```

`storage_state_path` is path reference only, not file contents.

## POST /api/scraper/yandex/session/check

Validate saved session still works (e.g., probe Yandex authenticated page).

**Response 200**:

```json
{
  "status": "valid | expired | needs_manual_action",
  "last_checked_at": "ISO8601"
}
```
