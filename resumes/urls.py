from django.urls import path

from . import views

app_name = "resumes"

urlpatterns = [
    path("upload/", views.upload_resume, name="upload"),
    path("<int:pk>/", views.resume_detail, name="detail"),
    path("<int:pk>/download/", views.download_resume, name="download"),
]