# iolm/tasks.py
from __future__ import annotations
import logging
import os
import io
import pandas as pd
import tempfile

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Tuple
from zipfile import ZipFile

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core.files.base import ContentFile
from django.utils import timezone
from celery.utils.log import get_task_logger

from django.conf import settings

from .models import UploadJob
from .services.ocr_iolm import process_iolm_image  # 네가 만든 모듈



logger = logging.getLogger("iolm.tasks")

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


# image_path 하나를 받아서
#  - rows: 엑셀에 들어갈 dict 리스트 (보통 OD/OS 2개 row)
#  - usage: OpenAI usage/코스트 정보 dict
# 를 반환
def run_ocr_for_image(image_path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    한 장의 IOLM 이미지 파일을 OpenAI OCR 파이프라인(process_iolm_image)에 넘겨서
    - OD / OS 각각 1row씩 (최대 2row) 엑셀용 dict 리스트를 만들고
    - 이 이미지 한 장에서 사용된 OpenAI 토큰/코스트 요약을 반환한다.
    """
    result = process_iolm_image(Path(image_path))

    ptnt = result.get("ptnt_info", {})
    od_obj = result.get("od", {}) or {}
    os_obj = result.get("os", {}) or {}
    usage = result.get("usage", {}) or {}

    # od/os는 {"measurements": [ {...} ], "wrong": 0} 구조
    od_meas_list = od_obj.get("measurements") or []
    os_meas_list = os_obj.get("measurements") or []

    od_meas = od_meas_list[0] if od_meas_list else None
    os_meas = os_meas_list[0] if os_meas_list else None

    img_name = os.path.basename(image_path)

    def build_row(eye_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            # 공통 patient 정보
            "source_image": img_name,
            "ptnt_name": ptnt.get("ptnt_name", ""),
            "ptnt_dob": ptnt.get("ptnt_dob", ""),
            "ptnt_sex": ptnt.get("ptnt_sex", ""),
            "ptnt_id": ptnt.get("ptnt_id", ""),
            "hospital": ptnt.get("hospital", ""),
            "exam_date": ptnt.get("exam_date", ""),
            # eye별 biometry
            "eye": eye_data.get("eye", ""),
            "LS": eye_data.get("LS", ""),
            "VS": eye_data.get("VS", ""),
            "LVC": eye_data.get("LVC", ""),
            "AL": eye_data.get("AL", 0.0),
            "ACD": eye_data.get("ACD", 0.0),
            "LT": eye_data.get("LT", 0.0),
            "CCT": eye_data.get("CCT", 0),
            "WTW": eye_data.get("WTW", 0.0),
            "K1": eye_data.get("K1", 0.0),
            "K1_m": eye_data.get("K1_m", 0),
            "K2": eye_data.get("K2", 0.0),
            "K2_m": eye_data.get("K2_m", 0),
            "TK1": eye_data.get("TK1", 0.0),
            "TK1_m": eye_data.get("TK1_m", 0),
            "TK2": eye_data.get("TK2", 0.0),
            "TK2_m": eye_data.get("TK2_m", 0),
            "missing_count": eye_data.get("missing_count", 0),
        }

    rows: List[Dict[str, Any]] = []
    if od_meas:
        rows.append(build_row(od_meas))
    if os_meas:
        rows.append(build_row(os_meas))

    # 2) usage 요약 (이 이미지 한 장의 총 cost를 하나의 숫자로 만들어 줌)
    total_cost = 0.0
    for part_key in ("ptnt", "od", "os"):
        part_usage = usage.get(part_key) or {}
        cost = part_usage.get("total_cost_usd")
        if isinstance(cost, (int, float)):
            total_cost += float(cost)

    image_usage: Dict[str, Any] = {
        "cost_usd": total_cost,
        "usage_raw": usage,  # 원한다면 raw usage도 같이 넣어 두기
    }

    return rows, image_usage



def _extract_zip_images(zip_file_field, tmpdir: str) -> List[str]:
    """
    ZIP FileField에서 이미지 확장자(IMAGE_EXTENSIONS)에 해당하는 파일만
    tmpdir 아래로 풀어서, 풀린 이미지 파일 경로 리스트를 반환한다.

    - S3 / 로컬 상관없이 zip_file_field.open(\"rb\") 로 읽어서 BytesIO로 감싼 뒤 ZipFile 사용
    - zip_file_field.path 에 의존하지 않으므로, DEFAULT_FILE_STORAGE 가 S3여도 안전
    """
    tmpdir_path = Path(tmpdir)
    image_paths: List[str] = []

    # 1) storage-agnostic하게 ZIP 전체 바이트 읽기
    with zip_file_field.open("rb") as f:
        zip_bytes = f.read()

    with ZipFile(io.BytesIO(zip_bytes)) as zf:
        # 디렉토리 제외 + 확장자 필터링
        image_names = [
            name
            for name in zf.namelist()
            if (
                not name.endswith("/") and
                Path(name).suffix.lower() in IMAGE_EXTENSIONS
            )
        ]

        image_names.sort()

        # 2) 선택된 이미지 파일만 tmpdir에 추출
        for name in image_names:
            dest_path = tmpdir_path / name
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            with zf.open(name) as src, open(dest_path, "wb") as dst:
                dst.write(src.read())

            image_paths.append(str(dest_path))

    return image_paths


def _build_usage_aggregator() -> Dict[str, Any]:
    return {
        "total_images": 0,
        "total_eyes": 0,
        "total_cost_usd": 0.0,
        "by_image": [],
    }


def _update_usage(usage_summary: Dict[str, Any], image_name: str, image_usage: Dict[str, Any], eye_count: int) -> None:
    usage_summary["total_images"] += 1
    usage_summary["total_eyes"] += eye_count
    cost = float(image_usage.get("cost_usd", 0.0))
    usage_summary["total_cost_usd"] += cost
    usage_summary["by_image"].append(
        {
            "image": image_name,
            "eyes": eye_count,
            "usage": image_usage,
        }
    )


@shared_task(bind=True)
def process_upload_job(self, job_id: int) -> None:
    task_id = self.request.id

    try:
        job = UploadJob.objects.get(pk=job_id)
    except UploadJob.DoesNotExist:
        logger.error(f"Job {job_id} not found.")
        return
    
    logger.info("START job=%s task=%s pid=%s", job.id, task_id, os.getpid())

    job.status = UploadJob.Status.PROCESSING
    job.processed_images = 0
    job.num_images = 0
    job.num_eyes = 0
    job.error_message = ""
    job.completed_at = None
    job.updated_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "processed_images",
            "num_images",
            "num_eyes",
            "error_message",
            "completed_at",
            "updated_at",
        ]
    )

    # ---- 소프트 타임리밋(작업 내부용) 설정 ----
    soft_limit = getattr(settings, "IOLM_TASK_SOFT_LIMIT", None)
    start_ts = time.monotonic()
    soft_timed_out = False

    usage_summary = _build_usage_aggregator()
    all_rows: List[Dict[str, Any]] = []
    total_eyes = 0

    try:
        with TemporaryDirectory() as tmpdir:
            # ⬇️ S3/로컬 모두 동작하도록 FileField 자체를 넘김
            image_paths = _extract_zip_images(job.zip_file, tmpdir)
            total_images = len(image_paths)

            # DB에 총 이미지 수 업데이트
            job.num_images = total_images
            job.updated_at = timezone.now()
            job.save(update_fields=["num_images", "updated_at"])

            for idx, image_path in enumerate(image_paths, start=1):
                filename = os.path.basename(image_path)
                logger.info(
                    "PROCESS job=%s task=%s idx=%s/%s file=%s pid=%s",
                    job.id,
                    task_id,
                    idx,
                    total_images,
                    filename,
                    os.getpid(),
                )

                rows, image_usage = run_ocr_for_image(image_path)
                eye_count = len(rows)
                total_eyes += eye_count
                all_rows.extend(rows)

                _update_usage(usage_summary, filename, image_usage, eye_count)

                # 진행률 업데이트
                job.processed_images = idx
                job.num_eyes = total_eyes
                UploadJob.objects.filter(pk=job.id).update(
                    processed_images=idx,
                    num_eyes=total_eyes,
                    updated_at=timezone.now(),
                )

            # 여기서 all_rows 를 가지고 엑셀 파일 생성
            excel_bytes, excel_filename = build_excel_in_memory(all_rows, job)

            # 루프 종료 후 최종 값 명시적으로 고정
            job.processed_images = total_images
            job.num_eyes = total_eyes

        # 결과 파일 저장 및 최종 상태 업데이트
        job.result_file.save(excel_filename, ContentFile(excel_bytes), save=False)

        job.status = UploadJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.usage_summary = usage_summary
        job.updated_at = job.completed_at

        job.save(
            update_fields=[
                "status",
                "completed_at",
                "result_file",
                "usage_summary",
                "num_images",
                "num_eyes",
                "processed_images",
                "updated_at",
            ]
        )

        logger.info(
            "DONE job=%s task=%s images=%s eyes=%s pid=%s",
            job.id,
            task_id,
            job.num_images,
            job.num_eyes,
            os.getpid(),
        )

    except SoftTimeLimitExceeded:
        # <= 소프트 타임리밋에 걸렸을 때: 지금까지 결과라도 저장
        logger.warning(
            "Soft time limit exceeded for job=%s task=%s (partial result will be saved)",
            job.id,
            task_id,
        )

        if all_rows:
            # 지금까지 처리된 눈 수로 num_eyes 세팅 후 파일 생성
            job.num_eyes = len(all_rows)
            result_bytes, filename = build_excel_in_memory(all_rows, job)
            job.result_file.save(
                filename,
                ContentFile(result_bytes),
                save=False,
            )

        job.status = UploadJob.Status.FAILED
        job.error_message = "Time limit exceeded (partial result saved)"
        job.completed_at = timezone.now()
        job.updated_at = job.completed_at
        job.usage_summary = usage_summary

        job.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "updated_at",
                "num_images",        # 있어도 문제 없음
                "num_eyes",
                "processed_images",  # 있어도 문제 없음 (위에서 세팅했다면)
                "result_file",
                "usage_summary",
            ]
        )
        # Celery 결과는 실패로 남기되, DB/파일에는 부분 결과 유지
        raise

    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "ERROR job=%s task=%s pid=%s: %s", job.id, task_id, os.getpid(), exc
        )
        job.status = UploadJob.Status.FAILED
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.updated_at = job.completed_at
        job.save(
            update_fields=[
                "status",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )
        raise



def build_excel_in_memory(
    rows: List[Dict[str, Any]],
    job: UploadJob,
) -> Tuple[bytes, str]:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "IOLM"

    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for r in rows:
            ws.append([r.get(h, "") for h in headers])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    timestamp = timezone.now().strftime("%Y-%m-%d %H-%M")
    eye_count = len(rows) if rows else 0  
    filename = f"{timestamp}_{eye_count} eyes_output.xlsx"

    return buf.getvalue(), filename



@shared_task
def cleanup_old_zips() -> None:
    """
    하루 지난 ZIP 파일(iolm/zips)을 S3/로컬에서 정리하는 주기 작업.

    조건:
    - status = completed
    - zip_file 이 존재하고 (isnull=False)
    - zip_deleted_at 이 아직 None
    - created_at 이 1일 이전
    """
    # cutoff = timezone.now() - timedelta(minutes=1)
    cutoff = timezone.now() - timedelta(days=1)

    qs = UploadJob.objects.filter(
        status=UploadJob.Status.COMPLETED,
        zip_file__isnull=False,
        zip_deleted_at__isnull=True,
        created_at__lt=cutoff,
    )

    logger.info(
        "cleanup_old_zips: 대상 job 수 = %s (cutoff=%s)",
        qs.count(),
        cutoff.isoformat(),
    )

    for job in qs.iterator():
        zip_name = job.zip_file.name

        # S3든 로컬이든 동일한 API: 실제 파일 삭제
        job.zip_file.delete(save=False)

        # zip_deleted_at만 기록 (필요하면 zip_file 필드까지 비워도 됨)
        job.zip_deleted_at = timezone.now()
        job.save(update_fields=["zip_deleted_at"])

        logger.info(
            "cleanup_old_zips: job=%s zip 삭제 완료 (name=%s)",
            job.id,
            zip_name,
        )














