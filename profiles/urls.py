from django.urls import path

from . import views

app_name = "profiles"

urlpatterns = [
    path("me/", views.my_profile, name="me"),
    path("import/<int:resume_pk>/", views.import_from_resume, name="import_from_resume"),
]