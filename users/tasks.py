from __future__ import annotations

import io
import logging

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

from weasyprint import HTML

from .models import UserConsent

logger = logging.getLogger(__name__)


@shared_task
def generate_consent_pdf_and_send_email(consent_id: int) -> None:
    try:
        consent = UserConsent.objects.select_related("user").get(pk=consent_id)
    except UserConsent.DoesNotExist:
        logger.warning("UserConsent %s not found", consent_id)
        return

    if not (consent.email_at_consent or getattr(consent.user, "email", None)):
        logger.info("UserConsent %s has no target email; skip email sending", consent_id)
        target_email = None
    else:
        target_email = consent.email_at_consent or consent.user.email

    # 1) HTML 렌더링
    context = {
        "consent": consent,
    }
    html = render_to_string("users/consent_pdf.html", context)

    # 2) HTML -> PDF
    pdf_io = io.BytesIO()
    HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf(pdf_io)
    pdf_io.seek(0)
    pdf_bytes = pdf_io.getvalue()

    # 3) S3 (media) 에 PDF 저장
    ts = timezone.localtime(consent.created_at)
    ts_str = ts.strftime("%Y%m%d_%H%M")
    filename = f"consent_{consent.user_id}_{ts_str}.pdf"

    consent.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)
    logger.info("UserConsent %s PDF saved to %s", consent.id, consent.pdf_file.name)

    # 4) 이메일 전송
    if not target_email:
        return

    subject = "[Axialis] 환자 개인정보 처리 위탁 및 국외 이전 동의서 사본"
    body_lines = [
        "안녕하세요.",
        "",
        "첨부된 PDF 파일은 Axialis 서비스 이용을 위해 귀하가 동의하신",
        "「환자 개인정보 처리 위탁 및 국외 이전 동의서」 사본입니다.",
        "",
        "동의 내용에 변경이 필요하시거나, 재동의를 원하실 경우",
        "Axialis 마이페이지의 동의서 화면에서 다시 진행해 주세요.",
        "",
        "- 본 메일은 발신 전용입니다.",
    ]
    body = "\n".join(body_lines)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "no-reply@axialis.ai"

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[target_email],
    )
    email.attach(filename, pdf_bytes, "application/pdf")

    email.send(fail_silently=False)
    logger.info("UserConsent %s PDF emailed to %s", consent.id, target_email)
