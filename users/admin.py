# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = (
        "id",
        "username",
        "realname",
        "nickname",
        "coins",
        "hospital_name",
        "kakao_id",
        "email",
        "is_staff",
        "is_active",
        "created_at",  # 생성 시점 표시
    )
    list_filter = ("is_staff", "is_active")
    search_fields = ("username", "realname", "nickname", "kakao_id", "email")
    ordering = ("id",)

    # created_at은 자동 생성 값이니까 읽기 전용으로
    readonly_fields = ("created_at",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Kakao Info", {"fields": ("kakao_id", "realname")}),
        (
            "Profile",
            {
                "fields": (
                    "nickname",
                    "nickname_change_date",
                    "profile_image",
                    "profile_image_thumbnail",
                    "is_default_image",
                    "hospital_name",
                    "coins",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "created_at",  # Axialis 최초 가입 시점
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "realname", "email", "password1", "password2"),
            },
        ),
    )
