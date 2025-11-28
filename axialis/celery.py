# axialis/celery.py
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "axialis.settings")

app = Celery("axialis")

# settings.py 에서 "CELERY_" prefix 가진 값들 읽어옴
app.config_from_object("django.conf:settings", namespace="CELERY")

# 각 app 의 tasks.py 자동 탐색
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self) -> None:
    print(f"Request: {self.request!r}")