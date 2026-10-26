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
- [x] Phase 1 — Environment setup
- [x] Phase 2 — Django project, apps, custom User model
- [x] Phase 3A — MySQL database connected