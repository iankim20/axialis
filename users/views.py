# users/views.py
from __future__ import annotations

import secrets
from typing import Any, Dict
from urllib.parse import urlencode

from django.core.paginator import Paginator
from iolm.models import UploadJob


import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.contrib.auth import logout as django_logout
from django.shortcuts import redirect, render
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import CustomUser, UserConsent
from .tasks import generate_consent_pdf_and_send_email


KAKAO_AUTH_HOST = getattr(settings, "KAKAO_AUTH_HOST", "https://kauth.kakao.com")
KAKAO_API_HOST = getattr(settings, "KAKAO_API_HOST", "https://kapi.kakao.com")
KAKAO_REDIRECT_URI = settings.KAKAO_REDIRECT_URI

KAKAO_LOGOUT_URL = "https://kauth.kakao.com/oauth/logout"

class KakaoAPIError(Exception):
    pass

def _build_kakao_login_url(request: HttpRequest, force_reauth: bool = False) -> str:
    state = secrets.token_urlsafe(16)
    request.session["kakao_oauth_state"] = state

    params = {
        "response_type": "code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "state": state,
        # 필요 동의항목만 최소로
        "scope": "profile_nickname profile_image",
    }

    # ★ 여기 추가: Kakao SSO 무시하고 매번 ID/비번 강제 입력
    if force_reauth:
        params["prompt"] = "login"

    return f"{KAKAO_AUTH_HOST}/oauth/authorize?{urlencode(params)}"



def _exchange_code_for_token(code: str) -> Dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code": code,
    }
    resp = requests.post(f"{KAKAO_AUTH_HOST}/oauth/token", data=data, timeout=5)
    if not resp.ok:
        raise KakaoAPIError(f"Token request failed: {resp.status_code} {resp.text}")
    return resp.json()


def _get_user_info(access_token: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(
        f"{KAKAO_API_HOST}/v2/user/me",
        headers=headers,
        timeout=5,
    )
    if not resp.ok:
        raise KakaoAPIError(f"User info failed: {resp.status_code} {resp.text}")
    return resp.json()


def _kakao_post(path: str, access_token: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
    }
    resp = requests.post(
        f"{KAKAO_API_HOST}{path}",
        headers=headers,
        timeout=5,
    )
    if not resp.ok:
        raise KakaoAPIError(f"Kakao API {path} failed: {resp.status_code} {resp.text}")
    return resp.json()


def login_view(request: HttpRequest) -> HttpResponse:
    """
    로그인 페이지.
    이미 인증된 상태라면 굳이 다시 로그인 화면을 보여주지 않고
    바로 대시보드로 리다이렉트한다.
    """
    if request.user.is_authenticated:
        return redirect("users:dashboard")

    return render(request, "users/login.html")


def kakao_login(request: HttpRequest) -> HttpResponse:
    """카카오 로그인 페이지로 리다이렉트."""
    if request.user.is_authenticated:
        return redirect("users:dashboard")
    
    # 항상 재인증 강제
    login_url = _build_kakao_login_url(request, force_reauth=True)
    return redirect(login_url)



def kakao_callback(request: HttpRequest) -> HttpResponse:
    """카카오 로그인 후 callback 처리."""
    error = request.GET.get("error")
    if error:
        messages.error(request, "카카오 로그인 중 오류가 발생했습니다.")
        return redirect("users:login")

    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code or not state:
        return HttpResponseBadRequest("Missing code or state")

    saved_state = request.session.pop("kakao_oauth_state", None)
    if not saved_state or saved_state != state:
        return HttpResponseBadRequest("Invalid state parameter")

    try:
        token_data = _exchange_code_for_token(code)
    except KakaoAPIError:
        messages.error(request, "카카오 인증에 실패했습니다. 다시 시도해주세요.")
        return redirect("users:login")

    access_token = token_data.get("access_token")
    if not access_token:
        messages.error(request, "카카오 토큰을 가져오지 못했습니다.")
        return redirect("users:login")

    # 사이트에서 자주 Kakao API를 호출하지 않을 예정이라 세션에만 저장
    request.session["kakao_access_token"] = access_token

    try:
        user_info = _get_user_info(access_token)
    except KakaoAPIError:
        messages.error(request, "카카오 사용자 정보를 가져오지 못했습니다.")
        return redirect("users:login")

    kakao_id = user_info.get("id")
    if kakao_id is None:
        messages.error(request, "카카오 사용자 ID를 찾을 수 없습니다.")
        return redirect("users:login")

    kakao_id_str = str(kakao_id)
    kakao_account = user_info.get("kakao_account", {}) or {}
    profile = kakao_account.get("profile", {}) or {}

    user, created = CustomUser.objects.get_or_create(kakao_id=kakao_id_str)

    # if created:  # 최초 가입 시 100포인트 지급 행사
    #     user.coins = 100

    if not user.username:
        user.username = f"kakao_{kakao_id_str}"

    profile_nickname = profile.get("nickname")
    if profile_nickname:
        user.realname = profile_nickname

    profile_image_url = profile.get("profile_image_url")
    if profile_image_url:
        user.profile_image = profile_image_url

    thumbnail_url = profile.get("thumbnail_image_url")
    if thumbnail_url:
        user.profile_image_thumbnail = thumbnail_url

    is_default_image = profile.get("is_default_image")
    if is_default_image is not None:
        user.is_default_image = is_default_image

    user.save()

    # Django 기본 백엔드로 로그인
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    # 로그인 후 이동: 대시보드
    return redirect("users:dashboard")



@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    user = request.user

    jobs_qs = UploadJob.objects.filter(user=user).order_by("-created_at")
    paginator = Paginator(jobs_qs, 10)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    latest_valid_consent = UserConsent.get_latest_valid(user)
    # ★ billing.PointLog 붙이기 전까지 임시로 빈 리스트 사용
    point_logs: list[Any] = []

    context = {
        "user": user,
        "jobs": page_obj.object_list,
        "page_obj": page_obj,
        "jobs_start_index": page_obj.start_index() - 1,
        # PointLog 는 나중에 billing 앱에서 구현 후 연결
        # "point_logs": PointLog.objects.filter(user=user).order_by("-created_at")[:50],
        "latest_valid_consent": latest_valid_consent,    
        "has_valid_consent": bool(latest_valid_consent), 
        "point_logs": point_logs,
    }
    return render(request, "users/dashboard.html", context)


@login_required
def consent_view(request: HttpRequest) -> HttpResponse:
    user = request.user

    latest_valid = UserConsent.get_latest_valid(user)
    latest_any = (
        UserConsent.objects.filter(user=user).order_by("-created_at").first()
    )

    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or reverse("iolm:upload")
    )

    if request.method == "POST":
        email = (request.POST.get("contact_email") or "").strip()
        if email:
            user.email = email
            user.save(update_fields=["email"])

        consent_processing = request.POST.get("consent_processing") == "on"
        consent_delegation = request.POST.get("consent_delegation") == "on"
        consent_overseas = request.POST.get("consent_overseas") == "on"
        confirm_authority = request.POST.get("confirm_authority") == "on"
        consent_medical_responsibility = (
            request.POST.get("consent_medical_responsibility") == "on"
        )

        all_checked = (
            consent_processing
            and consent_delegation
            and consent_overseas
            and confirm_authority
            and consent_medical_responsibility
        )

        if not all_checked:
            messages.error(
                request,
                "모든 필수 동의 항목에 체크해야 환자 정보 업로드가 가능합니다.",
            )
        else:
            now_ts = timezone.now()
            valid_days = getattr(settings, "CONSENT_VALID_DAYS", 365)
            valid_until = now_ts + timedelta(days=valid_days)
            policy_version = getattr(settings, "CONSENT_POLICY_VERSION", "")

            consent = UserConsent.objects.create(
                user=user,
                email_at_consent=email or user.email or "",
                policy_version=policy_version,
                valid_until=valid_until,
                consent_processing=consent_processing,
                consent_delegation=consent_delegation,
                consent_overseas=consent_overseas,
                confirm_authority=confirm_authority,
                consent_medical_responsibility=consent_medical_responsibility,
                ip_address=request.META.get("REMOTE_ADDR") or None,
                user_agent=request.META.get("HTTP_USER_AGENT") or "",
            )

            generate_consent_pdf_and_send_email.delay(consent.id)

            messages.success(
                request,
                "개인정보 처리 위탁 및 국외 이전 동의가 저장되었습니다. "
                "동의서 사본이 이메일로 발송됩니다.",
            )
            return redirect(next_url)

        # POST 실패 시에도 최신 유효/전체 동의 다시 계산
        latest_valid = UserConsent.get_latest_valid(user)
        latest_any = (
            UserConsent.objects.filter(user=user).order_by("-created_at").first()
        )

    context = {
        "user": user,
        "latest_valid_consent": latest_valid,
        "latest_consent": latest_any,
        "next_url": next_url,
        "policy_version": getattr(settings, "CONSENT_POLICY_VERSION", ""),
        "valid_days": getattr(settings, "CONSENT_VALID_DAYS", 365),
    }
    return render(request, "users/consent.html", context)




@login_required
def logout_view(request: HttpRequest) -> HttpResponse:
    """
    Kakao 토큰 무효화 + Django 세션 로그아웃.
    로그아웃 후에는 사이트 home(landing)으로 이동.
    """
    access_token = request.session.get("kakao_access_token")
    if access_token:
        try:
            _kakao_post("/v1/user/logout", access_token)
        except KakaoAPIError:
            # 카카오 쪽 실패 시에도 로컬 로그아웃은 진행
            pass

    request.session.pop("kakao_access_token", None)
    logout(request)
    return redirect("landing")  # 현재 프로젝트에서 landing이 홈 역할


@login_required
def unlink_view(request: HttpRequest) -> HttpResponse:
    """
    Kakao unlink(앱 연결 해제) + 로컬 계정 삭제(회원 탈퇴).
    POST 요청만 허용.
    """
    if request.method != "POST":
        return redirect("users:dashboard")

    access_token = request.session.get("kakao_access_token")
    user = request.user

    if access_token:
        try:
            _kakao_post("/v1/user/unlink", access_token)
        except KakaoAPIError:
            # unlink 실패해도 로컬 계정 삭제는 진행 (필요 시 로깅)
            pass

    # 세션 전체 삭제 + 유저 삭제
    request.session.flush()
    user.delete()

    messages.success(request, "회원 탈퇴가 완료되었습니다.")
    return redirect("landing")
