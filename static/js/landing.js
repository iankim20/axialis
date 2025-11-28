document.addEventListener("DOMContentLoaded", () => {
    setupPromo();
});

/* -------------------------------------------------------------------------- */
/* PROMO POPUP LOGIC */
/* -------------------------------------------------------------------------- */
function setupPromo() {
    const promoBox = document.getElementById("promoBox");
    const closeBtn = document.getElementById("closePromo");

    if (!promoBox) return;

    // 랜딩 페이지에서는 로드 후 1초 뒤에 자연스럽게 등장
    setTimeout(() => {
        promoBox.classList.remove("hidden");
    }, 1000);

    if (closeBtn) {
        closeBtn.addEventListener("click", () => {
            promoBox.classList.add("hidden");
        });
    }
}