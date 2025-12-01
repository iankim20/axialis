document.addEventListener("DOMContentLoaded", () => {
    setupPromo();
    setupVarsModal();
    setupZipUpload();
    setupSecurityCard();
});

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