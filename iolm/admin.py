from django.contrib import admin

from .models import UploadJob


@admin.register(UploadJob)
class UploadJobAdmin(admin.ModelAdmin):
    # 리스트에서 거의 모든 주요 필드/프로퍼티를 보여주기
    list_display = (
        "id",
        "user",
        "original_filename",
        "status",
        "num_images",
        "num_eyes",
        "processed_images",
        "progress_display",
        "has_result_file_flag",
        "partial_failure_flag",
        "process_time_display",
        "created_at",
        "completed_at",
        "zip_deleted_at",
        "result_deleted_at",
        "usage_summary_short",
        "error_message_short",
    )

    list_filter = (
        "status",
        "created_at",
        "completed_at",
        "zip_deleted_at",
        "result_deleted_at",
        "user",
    )

    search_fields = (
        "original_filename",
        "user__username",
        "user__realname",
        "user__email",
    )

    ordering = ("-created_at",)

    # 디테일 화면에서 읽기전용으로 보여줄 것들
    readonly_fields = (
        "created_at",
        "updated_at",
        "completed_at",
        "zip_deleted_at",
        "result_deleted_at",
        "zip_file",
        "result_file",
        "processed_images",
        "usage_summary",
        "error_message",
        "process_time_display",
    )

    fieldsets = (
        ("기본 정보", {
            "fields": (
                "user",
                "original_filename",
                "status",
            )
        }),
        ("파일", {
            "fields": (
                "zip_file",
                "result_file",
            )
        }),
        ("통계", {
            "fields": (
                "num_images",
                "processed_images",
                "num_eyes",
            )
        }),
        ("시간 정보", {
            "fields": (
                "created_at",
                "updated_at",
                "completed_at",
                "zip_deleted_at",
                "result_deleted_at",
                "process_time_display",
            )
        }),
        ("Usage / 에러 로그", {
            "fields": (
                "usage_summary",
                "error_message",
            )
        }),
    )

    def progress_display(self, obj: UploadJob) -> str:
        if not obj.num_images:
            return "0%"
        return f"{obj.progress_percent}%"

    progress_display.short_description = "진행률"

    def has_result_file_flag(self, obj: UploadJob) -> bool:
        return obj.has_result_file

    has_result_file_flag.short_description = "결과 파일"
    has_result_file_flag.boolean = True

    def partial_failure_flag(self, obj: UploadJob) -> bool:
        return obj.is_partial_failure

    partial_failure_flag.short_description = "부분 실패"
    partial_failure_flag.boolean = True

    def usage_summary_short(self, obj: UploadJob) -> str:
        if not obj.usage_summary:
            return ""
        text = str(obj.usage_summary)
        return text if len(text) <= 50 else text[:47] + "..."

    usage_summary_short.short_description = "Usage (요약)"

    def error_message_short(self, obj: UploadJob) -> str:
        if not obj.error_message:
            return ""
        text = obj.error_message.replace("\n", " ")
        return text if len(text) <= 50 else text[:47] + "..."

    error_message_short.short_description = "에러 메시지 (요약)"
