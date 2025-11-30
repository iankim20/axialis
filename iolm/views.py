from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse

from .models import UploadJob
from .tasks import process_upload_job   
from django.conf import settings

from zoneinfo import ZoneInfo
from django.utils import timezone


def upload_page(request):
    max_bytes = settings.IOLM_MAX_UPLOAD_BYTES
    max_mb = max_bytes // (1024 * 1024)

    return render(
        request,
        "iolm/upload.html",
        {
            "max_size_bytes": max_bytes,
            "max_size_mb": max_mb,
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
    job = get_object_or_404(UploadJob, pk=pk, user=request.user)

    data = {
        "status": job.status,
        "processed_images": job.processed_images or 0,
        "total_images": job.num_images or 0,
        "progress_percent": job.progress_percent,
        "completed": job.status == UploadJob.Status.COMPLETED,
        "failed": job.status == UploadJob.Status.FAILED,
    }
    return JsonResponse(data)
