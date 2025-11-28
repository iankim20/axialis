// 뒤로가기 캐시 방지
window.addEventListener("pageshow", function (event) {
    const navEntries = performance.getEntriesByType("navigation");
    const navType = navEntries && navEntries[0] ? navEntries[0].type : null;

    if (event.persisted || navType === "back_forward") {
        window.location.reload();
    }
});

document.addEventListener("DOMContentLoaded", () => {
    const pointsHistoryBtn = document.getElementById("btn-show-points-history");
    const chargeBtn = document.getElementById("btn-charge-points");
    const modal = document.getElementById("points-history-modal");
    const unlinkForm = document.getElementById("unlink-form");

    // ===== 공통 유틸 =====
    const getCookie = (name) => {
        if (!document.cookie) return null;
        const cookies = document.cookie.split(";");
        for (const cookie of cookies) {
            const trimmed = cookie.trim();
            if (trimmed.startsWith(name + "=")) {
                return decodeURIComponent(trimmed.substring(name.length + 1));
            }
        }
        return null;
    };

    const csrfToken = getCookie("csrftoken");

    const pad2 = (n) => (n < 10 ? "0" + n : String(n));

    const formatDateTime = (date) => {
        const y = date.getFullYear();
        const m = pad2(date.getMonth() + 1);
        const d = pad2(date.getDate());
        const hh = pad2(date.getHours());
        const mm = pad2(date.getMinutes());
        const ss = pad2(date.getSeconds());
        return `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
    };

    const formatDuration = (ms) => {
        if (!Number.isFinite(ms) || ms < 0) return "-";
        const totalSec = Math.floor(ms / 1000);
        const h = Math.floor(totalSec / 3600);
        const m = Math.floor((totalSec % 3600) / 60);
        const s = totalSec % 60;

        if (h > 0) return `${h}시간 ${m}분 ${s}초`;
        if (m > 0) return `${m}분 ${s}초`;
        return `${s}초`;
    };

    // ===== 포인트 모달 열기/닫기 =====
    const openModal = () => {
        if (!modal) return;
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
    };

    const closeModal = () => {
        if (!modal) return;
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
    };

    if (pointsHistoryBtn) {
        pointsHistoryBtn.addEventListener("click", () => openModal());
    }

    if (modal) {
        modal.addEventListener("click", (e) => {
            if (e.target === modal || e.target.hasAttribute("data-modal-close")) {
                closeModal();
            }
        });

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                closeModal();
            }
        });
    }

    // ===== 포인트 충전 버튼 (placeholder) =====
    if (chargeBtn) {
        chargeBtn.addEventListener("click", () => {
            alert("포인트 충전 기능은 곧 추가될 예정입니다.");
        });
    }

    // ===== 탈퇴 폼 확인 =====
    if (unlinkForm) {
        unlinkForm.addEventListener("submit", (e) => {
            const confirmed = window.confirm(
                "정말 탈퇴하시겠습니까?\n모든 계정 정보와 작업 내역이 삭제됩니다."
            );
            if (!confirmed) {
                e.preventDefault();
            }
        });
    }

    // ===== 다운로드: 파일명 링크 + 아이콘 =====
    const attachDownloadHandler = (el) => {
        if (!el) return;
        el.addEventListener("click", (e) => {
            e.preventDefault();
            const url = el.dataset.downloadUrl || el.getAttribute("href");
            if (!url || url === "#") return;

            const confirmed = window.confirm("결과 파일을 다운로드하시겠습니까?");
            if (confirmed) {
                window.location.href = url;
            }
        });
    };

    document
        .querySelectorAll("[data-download-url]")
        .forEach((el) => attachDownloadHandler(el));

    // ===== 작업 삭제 버튼 =====
    document.querySelectorAll("[data-delete-url]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const url = btn.dataset.deleteUrl;
            if (!url) return;

            const confirmed = window.confirm(
                "이 작업을 삭제하시겠습니까?\n(추후 복구가 불가능합니다.)"
            );
            if (!confirmed) return;

            const options = {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            };

            if (csrfToken) {
                options.headers["X-CSRFToken"] = csrfToken;
            }

            fetch(url, options)
                .then((response) => {
                    if (!response.ok) {
                        throw new Error("삭제 요청 실패");
                    }
                    const row = btn.closest("tr");
                    if (row) row.remove();
                })
                .catch(() => {
                    alert("작업 삭제 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.");
                });
        });
    });

    // ===== 진행률 / 상태 폴링 =====
    const pendingRows = Array.from(
        document.querySelectorAll("tr[data-status-url]")
    );

    const updateRowProgress = (row, data) => {
        const progressCell = row.querySelector(".status-progress-cell");
        if (!progressCell) return;

        const barFill = progressCell.querySelector("[data-progress-fill]");
        const textEl = progressCell.querySelector("[data-progress-text]");

        const processed = data.processed_images ?? 0;
        const total = data.total_images ?? 0;

        let percent = data.progress_percent;
        if (typeof percent !== "number" || Number.isNaN(percent)) {
            percent = total > 0 ? (processed / total) * 100 : 0;
        }

        let percentStr = percent.toFixed(1);
        if (percentStr.endsWith(".0")) {
            percentStr = percentStr.slice(0, -2);
        }

        const clamped = Math.max(0, Math.min(percent, 100));

        if (barFill) {
            barFill.style.width = `${clamped}%`;

            if (data.failed) {
                barFill.classList.add("progress-bar-fill-failed");
            }
        }

        if (textEl) {
            if (total > 0) {
                textEl.textContent = `${percentStr}% (${processed}/${total})`;
            } else if (data.failed) {
                textEl.textContent = "에러 발생";
            } else {
                textEl.textContent = "준비 중...";
            }
        }
    };

    const updateRowStatusAndTime = (row, data) => {
        const statusCol = row.querySelector(".status-col");
        const badge = statusCol ? statusCol.querySelector(".status-badge") : null;
        const subText = statusCol ? statusCol.querySelector(".status-subtext") : null;
        const completedAtCell = row.querySelector(".col-completed-at");

        if (!statusCol || !badge) return;

        // 실패 상태
        if (data.failed) {
            badge.classList.remove("status-badge-processing", "status-badge-completed");
            badge.classList.add("status-badge-failed");
            badge.textContent = "실패";

            if (subText) {
                subText.textContent = "처리 중 오류가 발생했습니다.";
            }
            if (completedAtCell) {
                completedAtCell.textContent = "-";
            }

            row.classList.remove("job-row-pending");
            row.classList.add("job-row-failed");
            row.removeAttribute("data-status-url");
            return;
        }

        // 완료 상태
        if (data.completed) {
            badge.classList.remove("status-badge-processing", "status-badge-failed");
            badge.classList.add("status-badge-completed");
            badge.textContent = "완료";

            const uploadedAtCell = row.querySelector(".col-uploaded-at");
            let durationText = "-";

            if (uploadedAtCell && uploadedAtCell.dataset.uploadedAt) {
                const uploadedDate = new Date(uploadedAtCell.dataset.uploadedAt);
                const now = new Date();
                durationText = formatDuration(now - uploadedDate);
            }

            if (subText) {
                subText.textContent = `처리 시간: ${durationText}`;
            }

            if (completedAtCell) {
                const now = new Date();
                completedAtCell.textContent = formatDateTime(now);
            }

            row.classList.remove("job-row-pending");
            row.classList.add("job-row-completed");
            row.removeAttribute("data-status-url");
        }
    };

    const pollProgressOnce = () => {
        pendingRows.forEach((row) => {
            const statusUrl = row.dataset.statusUrl;
            if (!statusUrl) return;

            fetch(statusUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
            })
                .then((response) => {
                    if (!response.ok) return null;
                    return response.json();
                })
                .then((data) => {
                    if (!data) return;
                    updateRowProgress(row, data);
                    updateRowStatusAndTime(row, data);
                })
                .catch(() => {
                    // 폴링 실패 시에는 조용히 무시
                });
        });
    };

    if (pendingRows.length > 0) {
        pollProgressOnce();
        setInterval(pollProgressOnce, 2000);
    }
});
