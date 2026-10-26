from django.urls import path

from . import views

app_name = "profiles"

urlpatterns = [
    path("me/", views.my_profile, name="me"),
    path("me/edit/", views.edit_profile, name="edit"),
    path("me/status/", views.change_my_status, name="change_status"),
    path("import/<int:resume_pk>/", views.import_from_resume, name="import_from_resume"),
]