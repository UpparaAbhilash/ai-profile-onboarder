"""Who may see which resume. Every resume view must use these helpers."""
from .models import Resume

SESSION_KEY = "uploaded_resume_ids"
MAX_REMEMBERED_UPLOADS = 20


def session_resume_ids(request) -> list[int]:
    return request.session.get(SESSION_KEY, [])


def remember_upload(request, resume: Resume) -> None:
    """Remember in the session that this browser uploaded the resume."""
    ids = session_resume_ids(request)
    if resume.pk not in ids:
        ids.append(resume.pk)
    request.session[SESSION_KEY] = ids[-MAX_REMEMBERED_UPLOADS:]  # reassign so Django saves it


def can_access_resume(request, resume: Resume) -> bool:
    user = request.user
    if user.is_authenticated:
        if user.has_perm("resumes.view_resume"):  # superusers and authorised reviewers
            return True
        if resume.owner_id == user.pk:
            return True
    return resume.pk in session_resume_ids(request)


def find_duplicate_upload(request, sha256: str):
    """Return an earlier upload of the same file by the SAME person, if any.

    We only look at the current user's / session's own uploads, so nobody can
    discover whether someone else uploaded a particular file.
    """
    same_file = Resume.objects.filter(sha256=sha256)
    if request.user.is_authenticated:
        own = same_file.filter(owner=request.user).first()
        if own:
            return own
    return same_file.filter(pk__in=session_resume_ids(request)).first()