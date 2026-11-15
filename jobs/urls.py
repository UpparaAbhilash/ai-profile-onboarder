from django.urls import path

from . import views

app_name = "jobs"

urlpatterns = [
    path("", views.job_list, name="list"),
    path("recommended/", views.recommended, name="recommended"),
    path("<int:pk>/", views.job_detail, name="detail"),
    path("<int:pk>/apply/", views.apply, name="apply"),
    path("<int:pk>/draft-cover-note/", views.draft_cover_note, name="draft_cover_note"),
    path("applications/", views.my_applications, name="my_applications"),
    path("applications/<int:pk>/withdraw/", views.withdraw, name="withdraw"),
]