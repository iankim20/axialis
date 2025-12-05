document.addEventListener('DOMContentLoaded', () => {
  // 1. 팝업 로직 (기존 유지)
  const closeBtn = document.getElementById('closePopupBtn');
  const popup = document.getElementById('promoPopup');

  if (closeBtn && popup) {
    closeBtn.addEventListener('click', () => {
      popup.style.opacity = '0';
      popup.style.transform = 'translateY(20px)';
      popup.style.transition = 'all 0.3s ease';
      setTimeout(() => { popup.style.display = 'none'; }, 300);
    });
  }

  // 2. Scroll Reveal (스크롤 애니메이션)
  const observerOptions = {
    threshold: 0.15,
    rootMargin: "0px 0px -50px 0px"
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  const revealElements = document.querySelectorAll('.reveal-item');
  revealElements.forEach(el => observer.observe(el));

  // 3. [NEW] 환불 정책 모달 로직
  const btnOpenRefund = document.getElementById('btnOpenRefund');
  const refundModal = document.getElementById('refundModal');
  const btnCloseRefund = document.getElementById('closeRefundBtn');

  if (btnOpenRefund && refundModal) {
    // 열기
    btnOpenRefund.addEventListener('click', (e) => {
      e.preventDefault();
      refundModal.classList.add('open');
    });

    // 닫기 (X 버튼)
    if (btnCloseRefund) {
      btnCloseRefund.addEventListener('click', () => {
        refundModal.classList.remove('open');
      });
    }

    // 닫기 (배경 클릭)
    refundModal.addEventListener('click', (e) => {
      if (e.target === refundModal) {
        refundModal.classList.remove('open');
      }
    });
  }
});