# iolm/urls.py
from django.urls import path

from . import views

app_name = "iolm"

urlpatterns = [
    # 업로드 페이지 (GET 전용, 로그인 여부에 따라 다른 화면)
    path("upload/", views.upload_page, name="upload"),

    # 🔹 브라우저 → S3 직접 업로드를 위한 presign / register API
    path("upload/presign/", views.upload_presign, name="upload_presign"),
    path("upload/register/", views.upload_register, name="upload_register"),

    # 실제 ZIP 업로드 처리 (POST) - (구) 백업용
    path("upload/submit/", views.upload_zip, name="upload_zip"),

    # 결과 엑셀 다운로드
    path("job/<int:pk>/download/", views.download_result, name="download_result"),

    # 작업 삭제
    path("job/<int:pk>/delete/", views.delete_job, name="delete_job"),

    path("jobs/<int:pk>/status/", views.upload_job_status, name="upload_job_status"),
]
