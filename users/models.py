from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.timezone import now


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
