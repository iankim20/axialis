document.addEventListener("DOMContentLoaded", () => {
    // ===============================================
    // 1. 공통 유틸 및 DOM 요소 선택
    // ===============================================
    const getCookie = (name) => {
        if (!document.cookie) return null;
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    };

    const csrfToken = getCookie("csrftoken");

    // 모달 관련
    const pointsHistoryBtn = document.getElementById("btn-show-points-history");
    const chargeBtn = document.getElementById("btn-charge-points");
    const modal = document.getElementById("points-history-modal");

    // 탈퇴 폼
    const unlinkForm = document.getElementById("unlink-form");

    // 폴링 대상 (processing 또는 pending 상태인 행)
    const pendingRows = Array.from(document.querySelectorAll("tr[data-status-url]"));
    let isReloading = false; // 중복 리로드 방지
    const formatLocalTimes = () => {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

        const dateFormatter = new Intl.DateTimeFormat(undefined, {
            timeZone: tz,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
        });

        const timeFormatter = new Intl.DateTimeFormat(undefined, {
            timeZone: tz,
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        });

        const datetimeFormatter = new Intl.DateTimeFormat(undefined, {
            timeZone: tz,
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        });

        const pad2 = (v) => String(v).padStart(2, "0");

        document.querySelectorAll("[data-utc]").forEach((el) => {
            const iso = el.dataset.utc;
            if (!iso) return;

            const d = new Date(iso);
            if (Number.isNaN(d.getTime())) return;

            const mode = el.dataset.format || "datetime";
            let text;

            if (mode === "date") {
                text = dateFormatter.format(d);     // ex) 2025-11-28
            } else if (mode === "time") {
                text = timeFormatter.format(d);     // ex) 04:19
            } else if (mode === "filename") {
                const eyes = el.dataset.eyes || "";
                const yyyy = d.getFullYear();
                const mm = pad2(d.getMonth() + 1);
                const dd = pad2(d.getDate());
                const hh = pad2(d.getHours());
                const mi = pad2(d.getMinutes());
                const suffix = eyes ? `${eyes}_eyes_output.xlsx` : "eyes_output.xlsx";
                // ex) 2025-11-28 13-05_6_eyes_output.xlsx
                text = `${yyyy}-${mm}-${dd} ${hh}-${mi}_${suffix}`;
            } else {
                text = datetimeFormatter.format(d); // 필요하면 다른 곳에서 사용
            }

            el.textContent = text;
        });
    };

    // 페이지 로드 시 한 번 전체 변환
    formatLocalTimes();

    const attachTimezoneToDownloadLinks = () => {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone; // ex) "Asia/Seoul"

        document.querySelectorAll("a[href*='/job/'][href$='/download/']").forEach((a) => {
            try {
                const url = new URL(a.href, window.location.origin);
                url.searchParams.set("tz", tz);
                a.href = url.toString();
            } catch (err) {
                console.warn("Invalid download url", a.href, err);
            }
        });
    };

    attachTimezoneToDownloadLinks();



    // ===============================================
    // 2. IOLM 진행률 폴링 로직
    // ===============================================

    const updateRow = (row, data) => {
        if (isReloading) return;

        // [핵심] 완료(Completed) 감지 시 페이지 즉시 새로고침 (이때 완료 시간, 파일명 등이 렌더링됨)
        if (
            data.status === "completed" ||
            (data.status === "failed" && data.has_result_file)
        ) {
            isReloading = true;
            window.location.reload();
            return;
        }

        // [실패] 처리
        if (data.status === 'failed') {
            const badge = row.querySelector(".badge");
            if (badge) {
                badge.className = "badge badge-danger";
                badge.textContent = "실패";
            }

            const statusTime = row.querySelector(".status-time");
            if (statusTime) statusTime.textContent = "오류 발생";

            const barFill = row.querySelector("[data-progress-fill]");
            if (barFill) barFill.classList.add("progress-fill-failed");

            row.removeAttribute("data-status-url");
            row.classList.remove("job-pending");

            // 더 이상 진행 중인 job이 없다면 밈 박스 숨김
            const memeBox = document.getElementById("dashboard-meme-box");
            if (memeBox && !document.querySelector("tr[data-status-url]")) {
                memeBox.classList.add("hidden");
            }
            return;
        }

        // [처리 중] 진행률 업데이트
        const barFill = row.querySelector("[data-progress-fill]");
        const textEl = row.querySelector("[data-progress-text]");

        const processed = data.processed_images ?? 0;
        const total = data.total_images ?? 0;
        const percent = Math.min(100, Math.max(0, data.progress_percent));

        if (barFill) {
            barFill.style.width = `${percent}%`;
        }

        if (textEl) {
            textEl.textContent = total > 0 ? `${percent}% (${processed}/${total})` : "대기 중...";
        }
    };

    const pollStatus = () => {
        if (isReloading) return;

        pendingRows.forEach(row => {
            const url = row.dataset.statusUrl;
            if (!url) return;

            fetch(url, {
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
                .then(res => res.ok ? res.json() : null)
                .then(data => {
                    if (data) updateRow(row, data);
                })
                .catch(console.warn);
        });
    };

    if (pendingRows.length > 0) {
        pollStatus();
        setInterval(pollStatus, 2000);
    }

    // ===============================================
    // 3. 작업 삭제 (Ajax)
    // ===============================================
    document.querySelectorAll("[data-delete-url]").forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            if (!confirm("정말 이 작업을 삭제하시겠습니까?\n결과 파일도 함께 삭제되며 복구할 수 없습니다.")) return;

            const url = btn.dataset.deleteUrl;
            fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest"
                }
            })
                .then(res => {
                    if (res.ok) window.location.reload();
                    else alert("삭제 실패");
                })
                .catch(() => alert("서버 오류"));
        });
    });

    // ===============================================
    // 4. 모달 및 기타 UI
    // ===============================================
    if (pointsHistoryBtn && modal) {
        pointsHistoryBtn.addEventListener("click", () => {
            modal.classList.add("is-open");
            modal.setAttribute("aria-hidden", "false");
        });
    }

    const closeModal = () => {
        if (!modal) return;
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
    };

    if (modal) {
        modal.addEventListener("click", (e) => {
            if (e.target === modal || e.target.closest("[data-modal-close]")) closeModal();
        });
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && modal.classList.contains("is-open")) closeModal();
        });
    }

    if (chargeBtn) {
        chargeBtn.addEventListener("click", () => alert("결제 기능 연동 준비 중입니다."));
    }

    if (unlinkForm) {
        unlinkForm.addEventListener("submit", (e) => {
            if (!confirm("정말 탈퇴하시겠습니까?\n모든 데이터가 영구 삭제됩니다.")) e.preventDefault();
        });
    }

    // ===============================================
    // 5. Dashboard Meme Box Logic (New)
    // ===============================================
    const setupDashboardMeme = () => {
        const memeBox = document.getElementById("dashboard-meme-box");
        const phraseEl = document.getElementById("dashboard-meme-text");

        // "처리 중(processing)" 또는 "대기(pending)" 상태인 작업이 있는지 확인
        // pendingRows는 상단에서 이미 정의됨 (tr[data-status-url])
        const hasActiveJobs = pendingRows.length > 0;

        if (!memeBox || !phraseEl) return;

        if (!hasActiveJobs) {
            memeBox.classList.add("hidden");
            return;
        }

        // 작업이 있으면 박스 표시
        memeBox.classList.remove("hidden");

        const phrases = [
            "AI 모델이 데이터를 정밀 추출 중입니다...",
            "백내장 수술의 성공을 기원합니다 🙏",
            "잠시 눈을 쉬게 해주세요. 모니터에서 멀어지세요 🌳",
            "IOLMaster 결과를 추출하여 엑셀로 정리해드립니다 🎁",
            "지금 이 순간에도 데이터는 안전하게 처리되고 있습니다.",
            "환자분들의 밝은 세상을 위해 노력하시느라 고생 많으십니다.",
            "데이터 추출 시간을 획기적으로 줄여드릴게요 ⚡",
            "세상에서 가장 동그란 CCC 그리는 중... ⭕",
            "슬릿램프 보느라 굽은 등, 잠시 기지개 켜세요 🧘‍♂️",
            "초음파 에너지(CDE) 최소로 쓰는 하루 되세요 📉",
            "Toric IOL 축 돌아가지 않게 기원하는 중... ",
            "Emmetropia 기원하는 중....",
            "난시 0 디옵터 간절히 비는 중...",
            "Endophthalmitis 발생 가능성 낮추는 중...",
            "환자 coop 올리는 중...",
            "Posterior Capsule 단단하게 만드는 중...",
            "동공 100% 산동 대기 중...",
            "Zonule 튼튼하게 연결하는 중...",
            "각막 부종 빼는 중...",
            "각막혼탁 없애는 중...",
            "Anterior Chamber 유지하는 중...",
            "각막내피 튼튼하게 만드는 중...",
            "Anterior Capsule Tension 낮추는 중...",
            "CME 발생 가능성 낮추는 중..."
        ];

        let currentIdx = Math.floor(Math.random() * phrases.length);
        phraseEl.textContent = phrases[currentIdx];

        // 10초(10000ms) 간격으로 변경
        setInterval(() => {
            let nextIdx;
            // 중복 방지 랜덤
            do {
                nextIdx = Math.floor(Math.random() * phrases.length);
            } while (nextIdx === currentIdx && phrases.length > 1);

            currentIdx = nextIdx;

            // 텍스트 교체 시 페이드 효과를 위해 클래스 재적용 (선택 사항)
            phraseEl.classList.remove("meme-dynamic");
            void phraseEl.offsetWidth; // trigger reflow
            phraseEl.classList.add("meme-dynamic");

            phraseEl.textContent = phrases[currentIdx];
        }, 10000);
    };

    // 실행
    setupDashboardMeme();


    window.addEventListener("pageshow", (event) => {
        const navEntries = performance.getEntriesByType("navigation");
        const navType = navEntries && navEntries[0] ? navEntries[0].type : null;
        const isBackForward = navType === "back_forward";

        if (event.persisted || isBackForward) {
            window.location.reload();
        }
    });
});