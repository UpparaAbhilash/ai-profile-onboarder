"""Root URL configuration: maps URL paths to views."""
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("accounts/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("jobs/", include("jobs.urls")),
    path("profiles/", include("profiles.urls")),
    path("resumes/", include("resumes.urls")),
    path("admin/", admin.site.urls),
]

# NOTE: MEDIA files (uploaded resumes) are intentionally NOT served here.
# Resumes are only delivered through resumes:download, which checks permissions.