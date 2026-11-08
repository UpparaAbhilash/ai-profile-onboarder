# Security

This document explains how the AI-Powered Profile Onboarder protects candidate data,
mapped to the [OWASP Top 10:2025](https://owasp.org/Top10/2025/).

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's
**Security → Report a vulnerability** (private advisory) on this repository.

## OWASP Top 10:2025

| # | Risk | How this project handles it |
|---|------|-----------------------------|
| A01 | Broken Access Control | No object IDs in URLs for a user's own data; every lookup is filtered by owner (`get_object_or_404(..., owner=request.user)`), so guessing IDs (IDOR) returns 404. Resumes are never served from `media/`: downloads go through a permission-checked view. Reviewers get a dedicated group with least-privilege permissions; the audit log needs its own permission. Tests check that other users' data is unreachable. |
| A02 | Security Misconfiguration | All secrets and environment-specific values live in `.env` (never committed). `DEBUG` is off by default. `check --deploy` passes in a production configuration. Security headers: Content Security Policy (no inline scripts), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`. HTTPS redirect, secure cookies and HSTS are switched on through environment variables. Redis is bound to `127.0.0.1` only. |
| A03 | Software Supply Chain Failures | All dependencies are pinned in `requirements.txt` / `requirements-dev.txt` and audited with `pip-audit` for known CVEs. Frontend libraries are loaded at a fixed version. |
| A04 | Cryptographic Failures | Passwords are hashed with PBKDF2 (Django default, about a million iterations; a test verifies it). Set-password and reset links are signed one-time tokens that expire. Full Aadhaar numbers are never stored: only the last 4 digits. Rate-limit counters use SHA-256 hashed keys, so the cache holds no emails or IP addresses. |
| A05 | Injection | The Django ORM uses parameterised queries; templates auto-escape output. CSV exports neutralise spreadsheet formulas (`=`, `+`, `-`, `@`). **Prompt injection:** resume text is sent to the AI as data inside delimiters, the AI must answer in a strict schema (Structured Outputs), and every extracted value is verified against the original text, so invented data is dropped. |
| A06 | Insecure Design | Business rules live in a service layer with explicit state machines (profile and application status). Data minimisation: CSV exports exclude contact details, date of birth and Aadhaar; Aadhaar numbers are redacted *before* text is sent to the AI. Background tasks receive only IDs, never personal data. |
| A07 | Authentication Failures | Login rate limiting: 5 failures per email or 20 per IP lock logins for 15 minutes, for the normal and the admin login. Password validators (minimum 10 characters, common and numeric passwords rejected). No account enumeration: password reset and lockout behave the same for unknown emails. Sessions expire after 8 hours; session cookies are `HttpOnly`. |
| A08 | Software or Data Integrity Failures | CSRF protection on every form. Uploaded PDFs are validated (real PDF signature, size and page limits) and stored under random file names. Celery accepts only JSON messages: pickle is disabled, because unpickling untrusted data can execute code. |
| A09 | Security Logging and Alerting Failures | An audit log records status changes, every reviewer view of a profile (with IP address) and every CSV export. Application logs contain IDs and error types only, never resume content. *Planned:* alerting on repeated lockouts in production. |
| A10 | Mishandling of Exceptional Conditions | OpenAI errors are classified as temporary (retried with backoff 30/60/120 s) or permanent (shown immediately). Uploads still work if Redis is down. A failed database write deletes the already stored PDF, so no orphan personal data remains. Timeouts are set for OpenAI, email and Celery tasks. |

## Personal data handled

| Data | Why it is needed | Protection |
|------|------------------|------------|
| Resume PDF | Source for the profile | Random file name, never publicly served, owner/reviewer access only |
| Name, email, phone | Contact and account | Not included in CSV exports |
| Date of birth | Part of the candidate profile | Never exported, not shown in lists |
| Aadhaar number | Part of the candidate profile (India) | Redacted before AI processing; only the last 4 digits are stored |

## Known limitations

- The login rate limit uses an in-memory cache locally; production will use Redis so all processes share the counters.
- Uploaded files are validated but not virus-scanned.