from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .views import landing

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", landing, name="landing"),

    path("users/", include("users.urls")),
    path("iolm/", include("iolm.urls")),
    path("billing/", include("billing.urls")),
]

# 추후 DEBUG를 FALSE로 바꿀것
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
