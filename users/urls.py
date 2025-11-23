# users/urls.py
from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("kakao/login/", views.kakao_login, name="kakao_login"),
    path("kakao/callback/", views.kakao_callback, name="kakao_callback"),

    path("dashboard/", views.dashboard, name="dashboard"),

    path("logout/", views.logout_view, name="logout"),
    path("logout_complete/", views.logout_complete_view, name="logout_complete"),
]
