"""Root URL configuration: maps URL paths to views."""
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    # Home page: a simple view that just renders a template.
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    # Django's built-in admin site.
    path("admin/", admin.site.urls),
]

# NOTE: we intentionally do NOT serve MEDIA files (uploaded resumes) here.
# Resumes contain personal data and will be served only through views
# that check the user's permissions (Phase 4).