# AI-Powered Profile Onboarder

A Django + Generative AI application that parses PDF resumes into structured
candidate profiles, creates accounts, scores profiles, and manages a job
application workflow.

## Tech stack
Python 3.13 · Django 5.2 LTS · MySQL · OpenAI API · PyMuPDF · Pydantic ·
Bootstrap · Celery + Redis

## Local setup (Windows PowerShell)
    py -3.13 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env   # then fill in values

## Progress
## Progress
## Progress
- [x] Phase 1 — Environment setup
- [x] Phase 2 — Django project, apps, custom User model
- [x] Phase 3A — MySQL database connected
- [x] Phase 3B — Core data models (resumes, profiles, jobs, applications, audit log)
- [x] Phase 4A — PDF validation and text extraction services
- [x] Phase 4B — Resume upload page, protected download, access control
- [x] Phase 5A — AI parser service: Pydantic schema, Aadhaar redaction, source verification, tests
- [x] Phase 5B — AI parsing in the upload flow, results page, reparse command
- [x] Phase 6A — Profile import from parsed resume, candidate login, My profile page
- [x] Phase 6B — Edit profile with validation, projects/certifications formsets, ownership tests
- [x] Phase 7A — Automatic accounts, set-password links, password reset, verified resume linking
- [x] Phase 7B — Real email delivery via SMTP (Gmail App Password), configured only through .env
- [x] Phase 8A — Profile status workflow (state machine, permissions, history, audit log)