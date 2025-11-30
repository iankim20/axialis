# iolm/urls.py
from django.urls import path

from . import views

app_name = "iolm"

urlpatterns = [
    # 업로드 페이지 (GET 전용, 로그인 여부에 따라 다른 화면)
    path("upload/", views.upload_page, name="upload"),

    # 실제 ZIP 업로드 처리 (POST)
    path("upload/submit/", views.upload_zip, name="upload_zip"),

    # 결과 엑셀 다운로드
    path("job/<int:pk>/download/", views.download_result, name="download_result"),

    # 작업 삭제
    path("job/<int:pk>/delete/", views.delete_job, name="delete_job"),

    path("jobs/<int:pk>/status/", views.upload_job_status, name="upload_job_status"),
]
