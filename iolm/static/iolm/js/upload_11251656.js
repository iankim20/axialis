document.addEventListener("DOMContentLoaded", () => {
    setupPromo();
    setupVarsModal();
    setupZipUpload();
});

/* 특별 이벤트 팝업 (로그인 X) ------------------------------------ */

function setupPromo() {
    const promoBox = document.getElementById("promoBox");
    const loginButton = document.getElementById("loginButton");
    const closePromo = document.getElementById("closePromo");

    if (!promoBox || !loginButton) return;

    const observer = new IntersectionObserver(
        entries => {
            const entry = entries[0];
            if (entry.isIntersecting) {
                promoBox.classList.remove("hidden");
            } else {
                promoBox.classList.add("hidden");
            }
        },
        { threshold: 0.5 }
    );

    observer.observe(loginButton);

    if (closePromo) {
        closePromo.addEventListener("click", () => {
            promoBox.classList.add("hidden");
        });
    }
}

/* 추출 변수 안내 모달 -------------------------------------------- */

function setupVarsModal() {
    const modal = document.getElementById("vars-modal");
    if (!modal) return;

    const openButtons = [
        document.getElementById("btn-open-vars-modal"),
        document.getElementById("btn-open-vars-modal-loggedin"),
    ].filter(Boolean);

    const closeButtons = modal.querySelectorAll("[data-modal-close]");

    openButtons.forEach(btn => {
        btn.addEventListener("click", () => {
            modal.classList.remove("hidden");
            modal.setAttribute("aria-hidden", "false");
        });
    });

    closeButtons.forEach(btn => {
        btn.addEventListener("click", () => hideModal(modal));
    });

    modal.addEventListener("click", event => {
        if (event.target === modal) {
            hideModal(modal);
        }
    });
}

function hideModal(modal) {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
}

/* ZIP 업로드 로직 (로그인 상태 전용) ------------------------------ */

function setupZipUpload() {
    const form = document.getElementById("zip-upload-form");
    if (!form) return;

    const dropArea = document.getElementById("drop-area");
    const fileInput = document.getElementById("zip-input");
    const fileInfo = document.getElementById("file-info");
    const fileNameEl = document.getElementById("file-name");
    const fileSizeEl = document.getElementById("file-size");
    const selectBtn = document.getElementById("btn-select-file");
    const resetBtn = document.getElementById("btn-reset");
    const uploadBtn = document.getElementById("btn-upload");

    const maxSize = parseInt(form.dataset.maxSize || "314572800", 10); // 300MB
    let currentFile = null;

    function showError(message) {
        const existing = document.querySelector(".error-popup");
        if (existing) existing.remove();

        const popup = document.createElement("div");
        popup.className = "error-popup";

        const close = document.createElement("button");
        close.textContent = "✕";
        close.addEventListener("click", () => popup.remove());

        const text = document.createElement("span");
        text.textContent = message;

        popup.appendChild(close);
        popup.appendChild(text);
        document.body.appendChild(popup);

        setTimeout(() => popup.remove(), 4000);
    }

    function formatSize(bytes) {
        if (bytes >= 1024 * 1024 * 1024) {
            return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
        }
        if (bytes >= 1024 * 1024) {
            return (bytes / (1024 * 1024)).toFixed(1) + " MB";
        }
        if (bytes >= 1024) {
            return (bytes / 1024).toFixed(0) + " KB";
        }
        return bytes + " B";
    }

    function handleFile(file) {
        if (!file) return;

        const nameLower = file.name.toLowerCase();
        if (!nameLower.endsWith(".zip")) {
            showError("ZIP 파일(.zip)만 업로드할 수 있습니다.");
            return;
        }

        if (file.size > maxSize) {
            showError("파일 용량이 300MB를 초과합니다. ZIP을 나누어 업로드해 주세요.");
            return;
        }

        currentFile = file;
        uploadBtn.disabled = false;

        fileNameEl.textContent = file.name;
        fileSizeEl.textContent = "파일 크기: " + formatSize(file.size);
        fileInfo.hidden = false;
    }

    function resetState() {
        currentFile = null;
        uploadBtn.disabled = true;
        fileInput.value = "";
        fileInfo.hidden = true;
    }

    // 선택 버튼 → 파일 선택
    selectBtn.addEventListener("click", () => {
        fileInput.click();
    });

    // input change
    fileInput.addEventListener("change", event => {
        const file = event.target.files[0];
        handleFile(file);
    });

    // drag & drop
    ["dragenter", "dragover"].forEach(type => {
        dropArea.addEventListener(type, event => {
            event.preventDefault();
            event.stopPropagation();
            dropArea.classList.add("drag-over");
        });
    });

    ["dragleave", "dragend"].forEach(type => {
        dropArea.addEventListener(type, event => {
            event.preventDefault();
            event.stopPropagation();
            dropArea.classList.remove("drag-over");
        });
    });

    dropArea.addEventListener("drop", event => {
        event.preventDefault();
        event.stopPropagation();
        dropArea.classList.remove("drag-over");

        const file = event.dataTransfer.files[0];
        handleFile(file);
    });

    // 초기화 버튼
    resetBtn.addEventListener("click", () => {
        resetState();
    });

    // 폼 submit 시 검증 + 로딩 스피너
    form.addEventListener("submit", event => {
        if (!currentFile) {
            event.preventDefault();
            showError("업로드할 ZIP 파일을 선택해 주세요.");
            return;
        }
        showLoadingOverlay();
    });

    /* 로딩 오버레이 */
    const messages = [
        "IOLM 이미지에서 각막 데이터를 정리하는 중...",
        "OD/OS를 분리해서 엑셀 행으로 구성하는 중...",
        "난시 수치와 축을 꼼꼼히 읽어오는 중...",
        "초점 거리와 굴절력을 검증하는 중...",
        "데이터 품질 지표를 확인하는 중...",
        "엑셀 파일을 마무리하는 중..."
    ];
    let msgIndex = 0;
    let msgTimer = null;

    function showLoadingOverlay() {
        const existing = document.querySelector(".loading-overlay");
        if (existing) return;

        const overlay = document.createElement("div");
        overlay.className = "loading-overlay";

        const loaderContainer = document.createElement("div");
        loaderContainer.className = "iol-loader-container";
        loaderContainer.innerHTML = `
      <svg width="52" height="52" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" class="iol-loader">
        <g transform="scale(-1,1) translate(-100,0)">
          <circle cx="50" cy="50" r="20" stroke="currentColor" stroke-width="4"/>
          <path d="M30 50 Q 20 50, 15 40 Q 10 30, 20 20" stroke="currentColor" stroke-width="4" fill="none"/>
          <path d="M70 50 Q 80 50, 85 60 Q 90 70, 80 80" stroke="currentColor" stroke-width="4" fill="none"/>
        </g>
      </svg>
    `;

        const text = document.createElement("p");
        text.id = "loadingText";

        overlay.appendChild(loaderContainer);
        overlay.appendChild(text);
        document.body.appendChild(overlay);

        msgIndex = 0;
        updateLoadingMessage();
        msgTimer = setInterval(updateLoadingMessage, 2500);
    }

    function updateLoadingMessage() {
        const text = document.getElementById("loadingText");
        if (!text) return;
        text.textContent = messages[msgIndex % messages.length];
        msgIndex += 1;
    }

    // 서버에서 리다이렉트되어 페이지를 떠나면 브라우저가 자동으로 DOM을 버리므로
    // 오버레이/interval 정리는 따로 할 필요가 거의 없다.
}
