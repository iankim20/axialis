# users/views.py
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from .models import CustomUser
import requests


KAKAO_AUTH_URL = "https://kauth.kakao.com/oauth/authorize"
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_USERINFO_URL = "https://kapi.kakao.com/v2/user/me"
KAKAO_REDIRECT_URI = settings.KAKAO_REDIRECT_URI
KAKAO_LOGOUT_REDIRECT_URI = settings.KAKAO_LOGOUT_REDIRECT_URI


def login_view(request):
    """일반 로그인 페이지 (카카오 로그인 버튼만 있는 페이지)."""
    return render(request, "users/login.html")


def kakao_login(request):
    """사용자를 카카오 로그인 페이지로 리다이렉트."""
    kakao_auth_url = (
        f"{KAKAO_AUTH_URL}"
        f"?client_id={settings.KAKAO_REST_API_KEY}"
        f"&redirect_uri={KAKAO_REDIRECT_URI}"
        f"&response_type=code"
    )
    return redirect(kakao_auth_url)


def kakao_callback(request):
    """카카오 로그인 후 callback 처리."""
    code = request.GET.get("code")
    if not code:
        return redirect("users:login")

    # 토큰 요청
    token_data = {
        "grant_type": "authorization_code",
        "client_id": settings.KAKAO_REST_API_KEY,
        "redirect_uri": KAKAO_REDIRECT_URI,
        "code": code,
    }
    token_response = requests.post(KAKAO_TOKEN_URL, data=token_data).json()
    access_token = token_response.get("access_token")

    if not access_token:
        return redirect("users:login")

    # 유저 정보 요청
    headers = {"Authorization": f"Bearer {access_token}"}
    user_info = requests.get(KAKAO_USERINFO_URL, headers=headers).json()

    kakao_id = user_info.get("id")
    kakao_account = user_info.get("kakao_account", {})
    profile = kakao_account.get("profile", {})

    # 유저 생성 또는 가져오기
    user, _ = CustomUser.objects.get_or_create(kakao_id=kakao_id)
    user.username = f"kakao_{kakao_id}"
    user.realname = profile.get("nickname")
    user.profile_image = profile.get("profile_image_url")
    user.profile_image_thumbnail = profile.get("thumbnail_image_url")
    user.is_default_image = profile.get("is_default_image")
    user.save()

    # Django 기본 백엔드로 로그인
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    # 로그인 후 이동 위치는 여기서 결정 (예: 마이페이지 or IOLM 업로드)
    return redirect("users:dashboard")


@login_required
def dashboard(request):
    """간단한 마이페이지 (나중에 확장)."""
    return render(request, "users/dashboard.html", {"user": request.user})


def logout_view(request):
    """카카오 로그아웃 URL로 리다이렉트 + Django 세션 로그아웃."""
    KAKAO_LOGOUT_URL = "https://kauth.kakao.com/oauth/logout"
    logout_url = (
        f"{KAKAO_LOGOUT_URL}"
        f"?client_id={settings.KAKAO_REST_API_KEY}"
        f"&logout_redirect_uri={KAKAO_LOGOUT_REDIRECT_URI}"
    )

    logout(request)
    return redirect(logout_url)


def logout_complete_view(request):
    messages.success(request, "안전하게 로그아웃되었습니다.")
    # 나중에 iolm:landing 만들면 거기로
    return redirect("landing")
