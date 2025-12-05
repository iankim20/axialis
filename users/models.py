from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now
from django.core.files.storage import default_storage  # 이미 있다면 생략 가능


from django.conf import settings
from django.utils import timezone
import os


class CustomUser(AbstractUser):
    kakao_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    realname = models.CharField(max_length=100, blank=True, null=True)

    profile_image = models.URLField(blank=True, null=True)
    profile_image_thumbnail = models.URLField(blank=True, null=True)
    is_default_image = models.BooleanField(blank=True, null=True)
    created_at = models.DateTimeField(default=now)

    nickname = models.CharField(max_length=50, default="", blank=True)
    nickname_change_date = models.DateTimeField(null=True, blank=True)

    # 앞으로 크레딧/건수 과금 모델에 쓸 수 있는 필드
    coins = models.PositiveIntegerField(default=0)

    # 병원/기관 정보
    hospital_name = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self) -> str:
        return self.username or f"kakao_{self.kakao_id}"


def consent_pdf_upload_to(instance: "UserConsent", filename: str) -> str:
    base = os.path.basename(filename)
    user_part = f"user_{instance.user_id}" if instance.user_id else "anonymous"
    
    return f"consents/{user_part}/{base}"


class UserConsent(models.Model):
    class Position(models.TextChoices):
        PROFESSOR = "prof", "교수"
        DIRECTOR = "director", "원장"
        STAFF = "staff", "봉직의"
        RESIDENT = "resident", "전공의"
        INTERN = "intern", "인턴"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="consents",
    )
    full_name = models.CharField("성명", max_length=100, blank=True, null=True)
    position = models.CharField(
        "직위",
        max_length=20,
        choices=Position.choices,
        blank=True,
        null=True,
    )
    email_at_consent = models.EmailField(blank=True)
    policy_version = models.CharField(
        max_length=32,
        default=getattr(settings, "CONSENT_POLICY_VERSION", ""),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField()

    # 개별 동의 항목
    consent_processing = models.BooleanField()
    consent_delegation = models.BooleanField()
    consent_overseas = models.BooleanField()
    confirm_authority = models.BooleanField()
    consent_medical_responsibility = models.BooleanField()

    # 모든 필수 항목이 체크되어 있는지 플래그
    is_fully_accepted = models.BooleanField(default=False)

    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)

    # 나중에 생성할 PDF 사본 (S3 / media backend 사용)
    pdf_file = models.FileField(
        upload_to=consent_pdf_upload_to,
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.is_fully_accepted = all(
            [
                self.consent_processing,
                self.consent_delegation,
                self.consent_overseas,
                self.confirm_authority,
                self.consent_medical_responsibility,
            ]
        )
        super().save(*args, **kwargs)

    @classmethod
    def get_latest_valid(cls, user):
        if not user or not getattr(user, "is_authenticated", False):
            return None

        now_ts = timezone.now()
        policy_version = getattr(settings, "CONSENT_POLICY_VERSION", "")

        return (
            cls.objects.filter(
                user=user,
                policy_version=policy_version,
                valid_until__gte=now_ts,
                is_fully_accepted=True,
            )
            .order_by("-created_at")
            .first()
        )




