# iolm/tasks.py
from __future__ import annotations
import logging
import os

import io
import tempfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Tuple
from zipfile import ZipFile

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils import timezone

import pandas as pd

from .models import UploadJob
from .services.ocr_iolm import process_iolm_image  # 네가 만든 모듈

logger = logging.getLogger("iolm.tasks")

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


# ---- 여기는 Evan이 이미 가지고 있는 OpenAI + cv2 파이프라인과 연결하는 래퍼 ----
# image_path 하나를 받아서
#  - rows: 엑셀에 들어갈 dict 리스트 (보통 OD/OS 2개 row)
#  - usage: OpenAI usage/코스트 정보 dict
# 를 반환하도록 구현하면 된다.
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



def _extract_zip_images(zip_path: str, tmpdir: str) -> List[str]:
    """
    ZIP 파일에서 이미지 확장자(IMAGE_EXTENSIONS)에 해당하는 파일만
    tmpdir 아래로 풀어서, 풀린 이미지 파일 경로 리스트를 반환한다.
    """
    tmpdir_path = Path(tmpdir)
    image_paths: List[str] = []

    # 1) ZIP을 전체 바이트로 읽어서 BytesIO로 감싸기
    with open(zip_path, "rb") as f:
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
            # 하위 디렉토리 구조가 있으면 만들어 주기
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

    job = UploadJob.objects.get(pk=job_id)
    logger.info("START job=%s task=%s pid=%s", job.id, task_id, os.getpid())

    job.status = UploadJob.Status.PROCESSING
    job.processed_images = 0
    job.error_message = ""
    job.completed_at = None
    job.save(update_fields=["status", "processed_images", "error_message", "completed_at"])

    usage_summary = _build_usage_aggregator()

    try:
        with TemporaryDirectory() as tmpdir:
            image_paths = _extract_zip_images(job.zip_file.path, tmpdir)
            total_images = len(image_paths)
            job.num_images = total_images
            job.save(update_fields=["num_images"])

            all_rows: List[Dict[str, Any]] = []
            total_eyes = 0

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

                # 진행률 업데이트 (race condition 줄이려고 update 사용)
                UploadJob.objects.filter(pk=job.id).update(
                    processed_images=idx,
                    num_eyes=total_eyes,
                    updated_at=timezone.now(),
                )

            # 여기서 all_rows 를 가지고 엑셀 파일 생성
            excel_bytes, excel_filename = build_excel_in_memory(all_rows, job)

        # 결과 파일 저장 및 최종 상태 업데이트
        job.result_file.save(excel_filename, ContentFile(excel_bytes))
        job.status = UploadJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.usage_summary = usage_summary
        job.save(update_fields=["status", "completed_at", "result_file", "usage_summary", "num_eyes"])

        logger.info(
            "DONE job=%s task=%s images=%s eyes=%s pid=%s",
            job.id,
            task_id,
            job.num_images,
            job.num_eyes,
            os.getpid(),
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("ERROR job=%s task=%s pid=%s: %s", job.id, task_id, os.getpid(), exc)
        job.status = UploadJob.Status.FAILED
        job.error_message = str(exc)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at"])
        raise


def build_excel_in_memory(rows: List[Dict[str, Any]], job: UploadJob) -> Tuple[bytes, str]:
    """
    rows(list[dict])를 받아서 in-memory 엑셀 바이너리(bytes)와 파일명을 반환.
    Evan이 기존에 쓰던 컬럼/포맷에 맞게 수정해도 된다.
    """
    import io

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
    eye_count = job.num_eyes or 0
    filename = f"{timestamp}_{eye_count} eyes_output.xlsx"

    return buf.getvalue(), filename



























# @shared_task
# def process_upload_job(job_id: int) -> None:
#     """
#     하나의 UploadJob에 대해:
#     - ZIP 안의 이미지 전부 꺼내서
#     - 각 이미지마다 OpenAI OCR 수행
#     - OD/OS 2개 row로 엑셀 DataFrame 구성
#     - result_file 저장 + usage_summary 채우기
#     """
#     try:
#         job = UploadJob.objects.get(pk=job_id)
#     except UploadJob.DoesNotExist:
#         # job 이 이미 지워졌다면 그냥 종료
#         return

#     # 상태 업데이트
#     job.status = UploadJob.Status.PROCESSING
#     job.error_message = ""
#     job.save(update_fields=["status", "error_message", "updated_at"])

#     rows: List[Dict[str, Any]] = []
#     usage_by_image: List[Dict[str, Any]] = []

#     try:
#         # 1) ZIP 파일 전체를 메모리로 읽기
#         field_file = job.zip_file
#         with field_file.open("rb") as f:
#             zip_bytes = f.read()

#         with ZipFile(io.BytesIO(zip_bytes)) as zf, tempfile.TemporaryDirectory() as tmpdir:
#             tmpdir_path = Path(tmpdir)

#             image_names = [
#                 name
#                 for name in zf.namelist()
#                 if (
#                     not name.endswith("/")  # 디렉토리 제외
#                     and Path(name).suffix.lower() in IMAGE_EXTENSIONS
#                 )
#             ]

#             image_names.sort()

#             for name in image_names:
#                 # ZIP 내부에서 파일 꺼내 임시 파일로 저장
#                 with zf.open(name) as img_file:
#                     img_data = img_file.read()

#                 tmp_image_path = tmpdir_path / Path(name).name
#                 tmp_image_path.parent.mkdir(parents=True, exist_ok=True)
#                 tmp_image_path.write_bytes(img_data)

#                 # 2) 한 장에 대해 IOLM OCR 수행
#                 res = process_iolm_image(tmp_image_path)

#                 ptnt = res["ptnt_info"]           # dict
#                 od_obj = res["od"]               # dict
#                 os_obj = res["os"]               # dict
#                 usage = res["usage"]             # dict: ptnt/od/os
#                 timing = res["timing"]

#                 # measurements 배열에서 첫 원소 꺼내기
#                 od_meas = od_obj["measurements"][0]
#                 os_meas = os_obj["measurements"][0]

#                 common = {
#                     "source_image": name,
#                     "ptnt_name": ptnt.get("ptnt_name", ""),
#                     "ptnt_dob": ptnt.get("ptnt_dob", ""),
#                     "ptnt_sex": ptnt.get("ptnt_sex", ""),
#                     "ptnt_id": ptnt.get("ptnt_id", ""),
#                     "hospital": ptnt.get("hospital", ""),
#                     "exam_date": ptnt.get("exam_date", ""),
#                 }

#                 def build_row(eye_data: Dict[str, Any]) -> Dict[str, Any]:
#                     return {
#                         **common,
#                         "eye": eye_data.get("eye", ""),
#                         "LS": eye_data.get("LS", ""),
#                         "VS": eye_data.get("VS", ""),
#                         "LVC": eye_data.get("LVC", ""),
#                         "AL": eye_data.get("AL", 0.0),
#                         "ACD": eye_data.get("ACD", 0.0),
#                         "LT": eye_data.get("LT", 0.0),
#                         "CCT": eye_data.get("CCT", 0),
#                         "WTW": eye_data.get("WTW", 0.0),
#                         "K1": eye_data.get("K1", 0.0),
#                         "K1_m": eye_data.get("K1_m", 0),
#                         "K2": eye_data.get("K2", 0.0),
#                         "K2_m": eye_data.get("K2_m", 0),
#                         "TK1": eye_data.get("TK1", 0.0),
#                         "TK1_m": eye_data.get("TK1_m", 0),
#                         "TK2": eye_data.get("TK2", 0.0),
#                         "TK2_m": eye_data.get("TK2_m", 0),
#                         "missing_count": eye_data.get("missing_count", 0),
#                     }

#                 rows.append(build_row(od_meas))
#                 rows.append(build_row(os_meas))

#                 usage_by_image.append(
#                     {
#                         "image": name,
#                         "usage": usage,
#                         "timing": timing,
#                     }
#                 )

#         # 3) DataFrame → 엑셀 메모리 파일로 만들기
#         if rows:
#             df = pd.DataFrame(rows)

#             buffer = io.BytesIO()
#             with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
#                 df.to_excel(writer, index=False, sheet_name="IOLM")

#             buffer.seek(0)

#             # 결과 파일 이름: filename_display 규칙을 따르되, 아직 completed_at 없으므로 대략적으로
#             now = timezone.now()
#             ts = now.strftime("%Y-%m-%d %H-%M")
#             filename = f"{ts}_{len(rows)}rows_output.xlsx"

#             job.result_file.save(filename, ContentFile(buffer.read()), save=False)
#         else:
#             # 이미지가 하나도 없으면 에러 처리
#             job.error_message = "ZIP 파일 내에서 유효한 이미지(.png/.jpg/.tif 등)를 찾지 못했습니다."
#             job.status = UploadJob.Status.FAILED
#             job.save(update_fields=["status", "error_message", "updated_at"])
#             return

#         # 4) usage 요약 계산 (간단 예: 총 이미지, 총 아이 수만)
#         total_images = len(usage_by_image)
#         total_eyes = len(rows)
#         # 비용 합산은 usage 안의 total_cost_usd 를 합치는 방식으로 구현 가능
#         total_cost = 0.0
#         for u in usage_by_image:
#             for part in ("ptnt", "od", "os"):
#                 part_usage = u["usage"].get(part) or {}
#                 cost = part_usage.get("total_cost_usd")
#                 if isinstance(cost, (int, float)):
#                     total_cost += float(cost)

#         job.num_images = total_images
#         job.num_eyes = total_eyes
#         job.completed_at = timezone.now()
#         job.status = UploadJob.Status.COMPLETED
#         job.usage_summary = {
#             "total_images": total_images,
#             "total_eyes": total_eyes,
#             "total_openai_cost_usd": round(total_cost, 6),
#             "by_image": usage_by_image,
#         }

#         job.save()

#     except Exception as exc:
#         # 실패 시 상태/에러만 기록
#         job.status = UploadJob.Status.FAILED
#         job.error_message = str(exc)
#         job.save(update_fields=["status", "error_message", "updated_at"])
