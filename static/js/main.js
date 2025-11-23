// 간단한 스크롤/CTA 핸들러 정도만
document.addEventListener("DOMContentLoaded", () => {
    const getStartedBtn = document.getElementById("cta-get-started");
    const loginBtn = document.getElementById("cta-login");
    const featuresSection = document.getElementById("features");

    if (getStartedBtn && featuresSection) {
        getStartedBtn.addEventListener("click", (e) => {
            e.preventDefault();
            featuresSection.scrollIntoView({ behavior: "smooth" });
        });
    }

    if (loginBtn) {
        loginBtn.addEventListener("click", (e) => {
            e.preventDefault();
            // 나중에 Kakao 로그인 URL로 교체
            // window.location.href = "/users/login/kakao/";
            console.log("TODO: redirect to Kakao login");
        });
    }
});
