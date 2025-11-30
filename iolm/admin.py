# iolm/admin.py
from django.contrib import admin

from .models import UploadJob


@admin.register(UploadJob)
class UploadJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "original_filename",
        "status",
        "created_at",
        "completed_at",
        "num_images",
        "processed_images",
        "num_eyes",
        "progress_display",
    )
    list_filter = (
        "status",
        "created_at",
        "completed_at",
    )
    search_fields = (
        "original_filename",
        "user__username",
        "user__realname",
        "user__email",
    )
    ordering = ("-created_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "completed_at",
        "error_message",
        "zip_file",
        "result_file",
        "processed_images",
        "usage_summary",
    )

    fieldsets = (
        ("기본 정보", {"fields": ("user", "original_filename", "status")}),
        ("파일", {"fields": ("zip_file", "result_file")}),
        ("통계", {"fields": ("num_images", "processed_images", "num_eyes")}),
        ("시간 정보", {"fields": ("created_at", "updated_at", "completed_at")}),
        ("Usage / 에러 로그", {"fields": ("usage_summary", "error_message")}),
    )

    def progress_display(self, obj: UploadJob) -> str:
        return f"{obj.progress_percent}%"

    progress_display.short_description = "진행률"
