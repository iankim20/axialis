# iolm/urls.py
from django.urls import path
from . import views

app_name = "iolm"

urlpatterns = [
    path("upload/", views.upload_view, name="upload"),
]
