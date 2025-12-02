document.addEventListener("DOMContentLoaded", () => {
    const uploadWidget = setupUploadWidget();
    setupPromo();
    setupVarsModal();
    setupZipUpload(uploadWidget);
    setupSecurityCard();
});

/* -------------------------------------------------------------------------- */
/* 0. GLOBAL UPLOAD STATUS WIDGET                                             */
/* -------------------------------------------------------------------------- */
function setupUploadWidget() {
    const STORAGE_KEY = "axialis_iolm_upload_widget_state_v1";
    const initialState = {
        status: "idle",          // idle | pending | complete
        lastFileName: "",
        lastFileSizeLabel: "",
        activeCount: 0
    };

    function formatMb(bytes) {
        if (!Number.isFinite(bytes) || bytes <= 0) return "";
        const mb = bytes / (1024 * 1024);
        return `${mb.toFixed(1)}MB`;
    }

    function loadState() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) return { ...initialState };
            const parsed = JSON.parse(raw);
            return { ...initialState, ...parsed };
        } catch {
            return { ...initialState };
        }
    }

    function saveState(state) {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch {
            // ignore
        }
    }

    const state = loadState();

    const widget = document.createElement("div");
    widget.id = "upload-status-widget";
    widget.className = "upload-status-widget upload-status-widget--hidden";
    widget.innerHTML = `
        <div class="upload-status-strip"></div>
        <div class="upload-status-inner">
            <div class="upload-status-header">
                <div class="upload-status-icon-row">
                    <div class="upload-status-icon-circle pending" data-role="icon-pending">
                        <div class="spinner-sm upload-status-spinner"></div>
                    </div>
                    <div class="upload-status-icon-circle complete" data-role="icon-complete" hidden>
                        <div class="upload-status-check"></div>
                    </div>
                    <div class="upload-status-title">
                        <span data-role="title-text">IOLM ZIP 업로드</span>
                        <span class="upload-status-chip pending" data-role="chip">연결 중</span>
                    </div>
                </div>
                <button
                    type="button"
                    class="upload-status-close hidden"
                    aria-label="상태 위젯 닫기"
                    data-role="close-btn"
                >
                    &times;
                </button>
            </div>
            <div class="upload-status-body">
                <p class="upload-status-main-text" data-role="main-text"></p>
                <p class="upload-status-meta" data-role="meta-text"></p>
                <p class="upload-status-warning" data-role="warning-text"></p>
            </div>
        </div>
    `;
    document.body.appendChild(widget);

    const chipEl = widget.querySelector("[data-role='chip']");
    const mainTextEl = widget.querySelector("[data-role='main-text']");
    const metaTextEl = widget.querySelector("[data-role='meta-text']");
    const warningTextEl = widget.querySelector("[data-role='warning-text']");
    const closeBtn = widget.querySelector("[data-role='close-btn']");
    const pendingIconEl = widget.querySelector("[data-role='icon-pending']");
    const completeIconEl = widget.querySelector("[data-role='icon-complete']");

    function render(currentState, options = {}) {
        const { pulse = false } = options;

        if (currentState.status === "idle") {
            widget.classList.remove("upload-status-widget--visible");
            widget.classList.add("upload-status-widget--hidden");
            widget.classList.remove("upload-status-widget--pulse");
            return;
        }

        widget.classList.add("upload-status-widget--visible");
        widget.classList.remove("upload-status-widget--hidden");

        if (currentState.status === "pending") {
            chipEl.textContent = "연결 중";
            chipEl.classList.add("pending");
            chipEl.classList.remove("complete");

            pendingIconEl.hidden = false;
            completeIconEl.hidden = true;

            mainTextEl.textContent = "업로드하신 파일을 AI 모델과 연결 중입니다...";
            metaTextEl.textContent = currentState.lastFileSizeLabel
                ? `파일 크기가 ${currentState.lastFileSizeLabel} 이므로 연결에 다소 시간이 소요됩니다.`
                : "";
            warningTextEl.textContent = "AI 모델과 연결 완료 시까지 절대 창을 닫지 마세요";

            closeBtn.classList.add("hidden");
            widget.classList.remove("upload-status-widget--pulse");
        } else if (currentState.status === "complete") {
            chipEl.textContent = "완료";
            chipEl.classList.remove("pending");
            chipEl.classList.add("complete");

            pendingIconEl.hidden = true;
            completeIconEl.hidden = false;

            mainTextEl.textContent = "zip 파일 연결이 완료 되었습니다. 창을 닫으셔도 됩니다";
            if (currentState.lastFileName) {
                metaTextEl.textContent = `${currentState.lastFileName} · ${currentState.lastFileSizeLabel}`;
            } else {
                metaTextEl.textContent = currentState.lastFileSizeLabel || "";
            }
            warningTextEl.textContent = "";

            closeBtn.classList.remove("hidden");

            if (pulse) {
                widget.classList.remove("upload-status-widget--pulse");
                void widget.offsetWidth;
                widget.classList.add("upload-status-widget--pulse");
            } else {
                widget.classList.remove("upload-status-widget--pulse");
            }
        }
    }

    render(state);

    closeBtn.addEventListener("click", () => {
        if (state.status !== "complete") return;
        state.status = "idle";
        state.lastFileName = "";
        state.lastFileSizeLabel = "";
        state.activeCount = 0;
        saveState(state);
        render(state);
    });

    window.addEventListener("storage", (event) => {
        if (event.key !== STORAGE_KEY || !event.newValue) return;
        try {
            const parsed = JSON.parse(event.newValue);
            state.status = parsed.status || "idle";
            state.lastFileName = parsed.lastFileName || "";
            state.lastFileSizeLabel = parsed.lastFileSizeLabel || "";
            state.activeCount = parsed.activeCount || 0;
            render(state);
        } catch {
            // ignore
        }
    });

    return {
        onUploadStarted(meta) {
            const sizeLabel = formatMb(meta.fileSizeBytes);
            state.status = "pending";
            state.lastFileName = meta.fileName;
            state.lastFileSizeLabel = sizeLabel;
            state.activeCount = (state.activeCount || 0) + 1;
            saveState(state);
            render(state);
        },
        onUploadFinished() {
            const wasPendingWithJobs =
                state.status === "pending" && (state.activeCount || 0) > 0;

            const nextCount = Math.max(0, (state.activeCount || 0) - 1);
            state.activeCount = nextCount;

            if (nextCount === 0 && wasPendingWithJobs) {
                state.status = "complete";
                saveState(state);
                render(state, { pulse: true });
            } else {
                saveState(state);
                render(state);
            }
        },
        resetAll() {
            state.status = "idle";
            state.lastFileName = "";
            state.lastFileSizeLabel = "";
            state.activeCount = 0;
            saveState(state);
            render(state);
        }
    };
}

/* -------------------------------------------------------------------------- */
/* 1. PROMO POPUP LOGIC */
/* -------------------------------------------------------------------------- */
function setupPromo() {
    const promoBox = document.getElementById("promoBox");
    const closeBtn = document.getElementById("closePromo");

    if (!promoBox) return;

    // 새로고침 시 무조건 다시 보임 (세션 스토리지 체크 제거)
    setTimeout(() => {
        promoBox.classList.remove("hidden");
    }, 500);

    if (closeBtn) {
        closeBtn.addEventListener("click", () => {
            promoBox.classList.add("hidden");
        });
    }
}

/* -------------------------------------------------------------------------- */
/* 2. VARIABLES MODAL LOGIC */
/* -------------------------------------------------------------------------- */
function setupVarsModal() {
    const modal = document.getElementById("vars-modal");
    if (!modal) return;

    const triggers = document.querySelectorAll("#btn-open-vars-modal-loggedin");
    const closeBtns = document.querySelectorAll("[data-modal-close]");

    triggers.forEach(btn => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            modal.classList.remove("hidden");
        });
    });

    closeBtns.forEach(btn => {
        btn.addEventListener("click", () => {
            modal.classList.add("hidden");
        });
    });

    modal.addEventListener("click", (e) => {
        if (e.target === modal) {
            modal.classList.add("hidden");
        }
    });
}

/* -------------------------------------------------------------------------- */
/* 3. SECURITY CARD COLLAPSIBLE LOGIC */
/* -------------------------------------------------------------------------- */
function setupSecurityCard() {
    const card = document.getElementById("securityCard");
    const toggle = document.getElementById("securityToggle");
    const wrapper = card?.querySelector(".security-content-wrapper");

    if (!card || !toggle || !wrapper) return;

    toggle.addEventListener("click", () => {
        // Toggle UI state
        wrapper.classList.toggle("collapsed");
        card.classList.toggle("expanded");
    });
}

/* -------------------------------------------------------------------------- */
/* 4. UPLOAD LOGIC (With JSZip & New Buttons) */
/* -------------------------------------------------------------------------- */
function setupZipUpload() {
    const form = document.getElementById("zip-upload-form");
    if (!form) return;

    const dropArea = document.getElementById("drop-area");
    const zipInput = document.getElementById("zip-input");

    // Views inside Drag Area
    const defaultView = dropArea.querySelector(".default-view");
    const analyzingView = dropArea.querySelector(".analyzing-view");
    const fileSelectedView = dropArea.querySelector(".file-selected-view");

    // Elements for data display
    const fileNameEl = document.getElementById("file-name");
    const fileSizeEl = document.getElementById("file-size");
    const imageCountEl = document.getElementById("image-count-display");
    const costEl = document.getElementById("estimated-cost");

    // Buttons 
    const browseBtn = document.getElementById("btn-browse-file");
    const resetBtn = document.getElementById("btn-reset");
    const analyzeBtn = document.getElementById("btn-analyze");

    const MAX_SIZE = parseInt(form.dataset.maxSize, 10);
    if (!Number.isFinite(MAX_SIZE)) {
        throw new Error("MAX_SIZE is not defined on #zip-upload-form");
    }

    // Helper Functions
    const formatSize = (bytes) => {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    };

    const isImageFile = (filename) => {
        return /\.(jpg|jpeg|png|tif|tiff|bmp)$/i.test(filename);
    };

    // State 1: Reset (No File)
    const resetUI = () => {
        zipInput.value = "";

        // Drag Area View
        defaultView.hidden = false;
        analyzingView.hidden = true;
        fileSelectedView.hidden = true;

        // Buttons
        // Browse: Active
        browseBtn.disabled = false;
        // Reset: Disabled
        resetBtn.disabled = true;
        // Analyze: Disabled
        analyzeBtn.disabled = true;

        // Data
        costEl.textContent = "0 P";
    };

    // State 2: File Loaded
    const updateUIForFile = (file, imgCount) => {
        // Drag Area View
        defaultView.hidden = true;
        analyzingView.hidden = true;
        fileSelectedView.hidden = false;

        // Display Info
        fileNameEl.textContent = file.name;
        fileSizeEl.textContent = formatSize(file.size);

        const points = imgCount * 2;

        if (imgCount > 0) {
            imageCountEl.textContent = `이미지 ${imgCount}장 감지됨`;
            costEl.textContent = `${points} P`;

            // Buttons
            // Browse: Disabled (Already selected)
            browseBtn.disabled = true;
            // Reset: Enabled (Select different)
            resetBtn.disabled = false;
            // Analyze: Enabled (Ready)
            analyzeBtn.disabled = false;

        } else {
            imageCountEl.textContent = "이미지 없음 (0장)";
            costEl.textContent = "0 P";

            browseBtn.disabled = true;
            resetBtn.disabled = false;
            analyzeBtn.disabled = true;
            alert("ZIP 파일 내에 유효한 이미지 파일이 없습니다.");
        }
    };

    const analyzeZip = async (file) => {
        // Show Spinner
        defaultView.hidden = true;
        analyzingView.hidden = false;

        try {
            const zip = await JSZip.loadAsync(file);
            let imgCount = 0;

            zip.forEach((relativePath, zipEntry) => {
                if (!zipEntry.dir && isImageFile(zipEntry.name)) {
                    if (!relativePath.startsWith("__MACOSX")) {
                        imgCount++;
                    }
                }
            });

            updateUIForFile(file, imgCount);

        } catch (e) {
            console.error(e);
            alert("ZIP 파일을 읽는 중 오류가 발생했습니다.");
            resetUI();
        }
    };

    const handleFiles = (files) => {
        if (files.length === 0) return;
        const file = files[0];

        if (!file.name.toLowerCase().endsWith(".zip")) {
            alert("ZIP 파일(.zip)만 업로드 가능합니다.");
            return;
        }
        if (file.size > MAX_SIZE) {
            alert(`파일 크기는 ${formatSize(MAX_SIZE)} 미만이어야 합니다.`);
            return;
        }

        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        zipInput.files = dataTransfer.files;

        analyzeZip(file);
    };


    // --- Event Listeners ---

    // 1. Drag & Drop on Drop Zone
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
        }, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.add('drag-over'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.remove('drag-over'), false);
    });

    dropArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        handleFiles(dt.files);
    });

    // Drop area click -> Trigger Browse (Only if no file selected, optional)
    dropArea.addEventListener('click', () => {
        // 파일이 없을 때만 드롭존 클릭으로 탐색기 오픈 허용
        if (!zipInput.value) {
            zipInput.click();
        }
    });

    // 2. Buttons
    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        zipInput.click();
    });

    resetBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        resetUI();
    });

    zipInput.addEventListener('change', function () {
        handleFiles(this.files);
    });

    // 3. Submit
    form.addEventListener('submit', () => {
        // Create Loading Overlay
        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.innerHTML = `
            <div class="spinner-sm" style="border-width:4px; width:50px; height:50px;"></div>
            <h3>데이터 업로드 및 분석 중...</h3>
            <p>잠시만 기다려주세요.</p>
        `;
        document.body.appendChild(overlay);
    });
}