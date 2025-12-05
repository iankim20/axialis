from __future__ import annotations

from typing import Any
import json
import boto3
from botocore.config import Config

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,  
)
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import UploadJob, iolm_zip_upload_to
import os
from .tasks import process_upload_job   
from django.conf import settings

from zoneinfo import ZoneInfo
from django.utils import timezone

from django.urls import reverse
from users.models import UserConsent

def _user_has_valid_consent(user) -> bool:
    return UserConsent.get_latest_valid(user) is not None


def upload_page(request):
    max_bytes = settings.IOLM_MAX_UPLOAD_BYTES
    max_mb = max_bytes // (1024 * 1024)

    has_valid_consent = False
    if request.user.is_authenticated:
        has_valid_consent = _user_has_valid_consent(request.user)



    return render(
        request,
        "iolm/upload.html",
        {
            "max_size_bytes": max_bytes,
            "max_size_mb": max_mb,
            "has_valid_consent": has_valid_consent,              
            "consent_url": reverse("users:consent"),             
        },
    )


@login_required
def upload_zip(request: HttpRequest) -> HttpResponse:
    """
    ZIP 업로드 처리:
    - UploadJob 레코드 생성
    - ZIP 파일 저장
    - 이후 Celery 작업이 잡아서 처리하게 연결 (다음 단계에서 추가)
    """
    if request.method != "POST":
        return redirect("iolm:upload")

    zip_file = request.FILES.get("zip_file")
    if not zip_file:
        messages.error(request, "업로드할 ZIP 파일을 선택해 주세요.")
        return redirect("iolm:upload")

    if zip_file.size > settings.IOLM_MAX_UPLOAD_BYTES:
        from django.utils.translation import gettext as _  # 안 쓰면 생략 가능
        messages.error(request, "파일 크기는 최대 200MB까지 업로드할 수 있습니다.")
        return redirect("iolm:upload")

    job = UploadJob.objects.create(
        user=request.user,
        zip_file=zip_file,
        original_filename=zip_file.name,
        status=UploadJob.Status.PENDING,
    )

    process_upload_job.delay(job.pk)


    messages.success(
        request,
        "IOLM ZIP 업로드가 접수되었습니다. 작업 진행 상황은 마이페이지에서 확인할 수 있습니다.",
    )
    return redirect("users:dashboard")

@login_required
@require_POST
def upload_presign(request: HttpRequest) -> JsonResponse:
    """
    브라우저에서 직접 S3로 ZIP을 올리기 위한 presigned POST를 발급한다.

    1) 요청 JSON 검증
    2) UploadJob 레코드를 미리 하나 만들고 (상태: pending)
    3) 그 job이 사용할 S3 key로 presigned POST 생성
    """
    user = request.user
    if not _user_has_valid_consent(user):
        return JsonResponse(
            {
                "error": "CONSENT_REQUIRED",
                "consent_url": reverse("users:consent"),
            },
            status=403,
        )


    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    filename = (payload.get("filename") or "").strip()
    size_bytes = int(payload.get("size_bytes") or 0)
    image_count = int(payload.get("image_count") or 0)
    expected_points = int(payload.get("expected_points") or 0)  # 현재는 저장 안 함

    if not filename or size_bytes <= 0:
        return JsonResponse({"error": "filename/size_bytes required"}, status=400)

    max_bytes = settings.IOLM_MAX_UPLOAD_BYTES
    if size_bytes > max_bytes:
        max_mb = max_bytes // (1024 * 1024)
        return JsonResponse(
            {"error": f"파일 크기는 최대 {max_mb}MB까지 업로드할 수 있습니다."},
            status=400,
        )

    # UploadJob 인스턴스를 만들고, zip_file.name 에만 S3 key를 미리 심어둠
    job = UploadJob(
        user=request.user,
        original_filename=filename,
        status=UploadJob.Status.PENDING,
        processed_images=0,
        error_message="",
    )
    if image_count > 0:
        job.num_images = image_count

    # models.iolm_zip_upload_to 와 동일 규칙으로 key 생성
    key = iolm_zip_upload_to(job, filename)
    job.zip_file.name = key
    job.save()

    bucket_name = settings.AWS_STORAGE_BUCKET_NAME
    region_name = getattr(settings, "AWS_S3_REGION_NAME", None)
    s3_client = boto3.client("s3", region_name=region_name, config=Config())

    # 10분짜리 presigned POST
    presigned_post = s3_client.generate_presigned_post(
        Bucket=bucket_name,
        Key=key,
        Fields={
            "Content-Type": "application/zip",
            "x-amz-server-side-encryption": "aws:kms",
        },
        Conditions=[
            {"Content-Type": "application/zip"},
            {"x-amz-server-side-encryption": "aws:kms"},
            ["content-length-range", 0, max_bytes],
        ],
        ExpiresIn=600,  # 10 minutes
    )

    return JsonResponse(
        {
            "job_id": job.pk,
            "upload": presigned_post,  # JS에서 upload.url / upload.fields 사용
        }
    )


@login_required
@require_POST
def upload_register(request: HttpRequest) -> JsonResponse:
    """
    브라우저 → S3 업로드가 끝난 뒤 호출되는 엔드포인트.

    - job_id 를 받아서 본인 소유 UploadJob 인지 확인
    - 아직 처리 중이 아니면 Celery task 큐잉
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body"}, status=400)

    job_id = payload.get("job_id")
    if not job_id:
        return JsonResponse({"error": "job_id required"}, status=400)

    job = get_object_or_404(UploadJob, pk=job_id, user=request.user)

    if job.status == UploadJob.Status.PENDING:
        process_upload_job.delay(job.pk)

    return JsonResponse({"job_id": job.pk})



@login_required
def download_result(request: HttpRequest, pk: int) -> HttpResponse:
    """
    결과 엑셀 다운로드.
    - 본인 소유 UploadJob만 접근 가능
    - 결과 파일이 아직 없으면 에러 메시지 후 대시보드로.
    """
    job = get_object_or_404(UploadJob, pk=pk, user=request.user)

    if not job.result_file:
        messages.error(request, "아직 결과 파일이 생성되지 않았습니다.")
        return redirect("users:dashboard")

    try:
        file_handle = job.result_file.open("rb")
    except FileNotFoundError:
        raise Http404("파일을 찾을 수 없습니다.")

    # === NEW: 클라이언트 타임존을 이용해 로컬 시간 기준 파일명 생성 ===
    completed = job.completed_at or job.created_at

    tz_name = request.GET.get("tz")  # ex) "Asia/Seoul"
    if tz_name:
        try:
            user_tz = ZoneInfo(tz_name)
            completed_local = completed.astimezone(user_tz)
        except Exception:
            # 잘못된 tz 문자열이 와도 그냥 서버 기본 타임존 기준으로 처리
            completed_local = timezone.localtime(completed)
    else:
        completed_local = timezone.localtime(completed)

    if job.num_eyes:
        ts = completed_local.strftime("%Y-%m-%d %H-%M")
        filename = f"{ts}_{job.num_eyes} eyes_output.xlsx"
    else:
        # 안전망: 기존 로직 유지
        filename = job.filename_display or "iolm_result.xlsx"

    response = FileResponse(file_handle, as_attachment=True, filename=filename)
    return response



@login_required
def delete_job(request: HttpRequest, pk: int) -> HttpResponse:
    """
    작업 삭제.
    - POST 요청을 기준으로 처리 (프론트에서 fetch/폼으로 호출)
    - ZIP / 결과 파일도 스토리지에서 같이 삭제.
    """
    job = get_object_or_404(UploadJob, pk=pk, user=request.user)

    if request.method == "POST":
        if job.result_file:
            job.result_file.delete(save=False)
        if job.zip_file:
            job.zip_file.delete(save=False)
        job.delete()
        messages.success(request, "작업이 삭제되었습니다.")
        return redirect("users:dashboard")

    # GET으로 직접 접근 시에는 그냥 대시보드로
    return redirect("users:dashboard")

@login_required
def upload_job_status(request, pk: int) -> JsonResponse:
    """
    Ajax 폴링용: 특정 UploadJob의 진행 상황을 JSON으로 반환.
    """
    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        return HttpResponseBadRequest("AJAX only")
        
    job = get_object_or_404(UploadJob, pk=pk, user=request.user)

    data = {
        "status": job.status,
        "processed_images": job.processed_images or 0,
        "total_images": job.num_images or 0,
        "progress_percent": job.progress_percent,
        "completed": job.status == UploadJob.Status.COMPLETED,
        "failed": job.status == UploadJob.Status.FAILED,
        "has_result_file": bool(job.result_file),
    }
    return JsonResponse(data)
