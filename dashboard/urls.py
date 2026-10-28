from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("candidates/", views.candidate_list, name="candidate_list"),
    path("candidates/<int:pk>/", views.candidate_detail, name="candidate_detail"),
    path("candidates/<int:pk>/review/", views.review_candidate, name="review_candidate"),
    path("applications/<int:pk>/status/", views.application_status, name="application_status"),
]