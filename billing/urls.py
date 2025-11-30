# billing/urls.py
from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("history/", views.payment_history, name="history"),
]
