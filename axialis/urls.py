from django.contrib import admin
from django.urls import path
from .views import landing

from django.contrib import admin
from django.urls import path, include
from .views import landing  # 기존 landing view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", landing, name="landing"),

    path("users/", include("users.urls")),
    path("iolm/", include("iolm.urls")),
    path("billing/", include("billing.urls")),
]

