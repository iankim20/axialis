from __future__ import annotations
import os
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.urls import reverse

def iolm_zip_upload_to(instance: "UploadJob", filename: str) -> str:
    """
    per-user 경로로 ZIP 저장:
    iolm/zips/user_<user_id>/<basename>
    """
    base = os.path.basename(filename)
    user_part = f"user_{instance.user_id}" if instance.user_id else "anonymous"
    return f"iolm/zips/{user_part}/{base}"


def iolm_result_upload_to(instance: "UploadJob", filename: str) -> str:
    """
    per-user 경로로 결과 엑셀 저장:
    iolm/results/user_<user_id>/<basename>
    """
    base = os.path.basename(filename)
    user_part = f"user_{instance.user_id}" if instance.user_id else "anonymous"
    return f"iolm/results/{user_part}/{base}"



class UploadJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "대기"
        PROCESSING = "processing", "처리 중"
        COMPLETED = "completed", "완료"
        FAILED = "failed", "실패"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="iolm_jobs",
    )

    zip_file = models.FileField(
        upload_to=iolm_zip_upload_to,
        help_text="사용자가 업로드한 원본 ZIP 파일",
    )
    result_file = models.FileField(
        upload_to=iolm_result_upload_to,
        blank=True,
        null=True,
        help_text="AI 추출 후 생성된 엑셀 파일",
    )

    original_filename = models.CharField(max_length=255)

    num_images = models.PositiveIntegerField(blank=True, null=True)
    num_eyes = models.PositiveIntegerField(blank=True, null=True)
    
    # 진행률: 지금까지 처리된 이미지 수
    processed_images = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    zip_deleted_at = models.DateTimeField(blank=True, null=True)

    error_message = models.TextField(blank=True)

    # OpenAI usage 등 집계용 JSON
    usage_summary = models.JSONField(blank=True, null=True, default=dict)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"IOLM Upload #{self.pk} ({self.user})"

    # === Dashboard / 템플릿에서 쓰는 helper ===

    @property
    def process_time_display(self) -> str:
        if not self.completed_at:
            return ""
        delta: timedelta = self.completed_at - self.created_at
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}초"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}분 {sec}초"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}시간 {minutes}분"

    @property
    def filename_display(self) -> str:
        if self.completed_at and self.num_eyes:
            ts = self.completed_at.strftime("%Y-%m-%d %H-%M")
            return f"{ts}_{self.num_eyes} eyes_output.xlsx"
        if self.result_file:
            return self.result_file.name.rsplit("/", 1)[-1]
        return ""

    @property
    def download_url(self) -> str:
        if not self.result_file:
            return ""
        return reverse("iolm:download_result", kwargs={"pk": self.pk})

    @property
    def delete_url(self) -> str:
        return reverse("iolm:delete_job", kwargs={"pk": self.pk})

    @property
    def progress_percent(self) -> int:
        if not self.num_images:
            return 0
        if self.processed_images >= self.num_images:
            return 100
        return int(self.processed_images * 100 / self.num_images)
