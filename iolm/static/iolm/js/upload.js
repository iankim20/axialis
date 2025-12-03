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

    const presignUrl = form.dataset.presignUrl || "";
    const registerUrl = form.dataset.registerUrl || "";
    const csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
    const csrfToken = csrfInput ? csrfInput.value : "";

    let currentFile = null;
    let currentImageCount = 0;




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

    const overlayPhrases = [
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



    // State 1: Reset (No File)
    const resetUI = () => {
        zipInput.value = "";
        currentFile = null;
        currentImageCount = 0;

        // Drag Area View
        defaultView.hidden = false;
        analyzingView.hidden = true;
        fileSelectedView.hidden = true;

        // Buttons
        browseBtn.disabled = false;
        resetBtn.disabled = true;
        analyzeBtn.disabled = false; // 기본 값은 비활성화지만, updateUIForFile이 다시 조정

        // Data
        costEl.textContent = "0 P";
        imageCountEl.textContent = "이미지 없음 (0장)";
        fileNameEl.textContent = "-";
        fileSizeEl.textContent = "-";
    };

    // State 2: File Loaded
    const updateUIForFile = (file, imgCount) => {
        currentFile = file;
        currentImageCount = imgCount;

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

    /* upload.js 내부의 createUploadOverlay 함수 교체 */

    /* upload.js 내부의 createUploadOverlay 함수 전체 교체 */

    const createUploadOverlay = (file) => {
        const overlay = document.createElement("div");
        overlay.className = "loading-overlay";

        overlay.innerHTML = `
            <div class="upload-loading-panel">
                <div class="upload-header">
                    <div class="spinner-lg"></div>
                    <h3 data-role="status-title">제출한 ZIP 파일을 AI 모델과 연결 중입니다</h3>
                    <p class="warning-text">
                        ⚠️ 완료 시까지 <strong>브라우저 창을 절대 닫지 마세요.</strong>
                    </p>
                </div>

                <div class="meme-container">
                    <p class="meme-text" data-role="phrase-text">
                        AI 모델 연결 대기 중...
                    </p>
                </div>

                <div class="upload-progress-container">
                    <div class="progress-labels">
                        <span class="file-info">${file.name}</span>
                        <span class="percent-text" data-role="progress-percent">0%</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-fill" data-role="progress-bar"></div>
                    </div>
                    <div class="progress-bytes" data-role="progress-bytes">
                        0 / ${formatSize(file.size)}
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const progressBar = overlay.querySelector('[data-role="progress-bar"]');
        const percentEl = overlay.querySelector('[data-role="progress-percent"]');
        const bytesEl = overlay.querySelector('[data-role="progress-bytes"]');
        const phraseEl = overlay.querySelector('[data-role="phrase-text"]');
        const titleEl = overlay.querySelector('[data-role="status-title"]');
        const warningEl = overlay.querySelector('.warning-text'); // 경고 문구 제어용
        const spinner = overlay.querySelector('.spinner-lg');

        // 1. 처음 뜰 때부터 랜덤으로 시작
        let currentIdx = Math.floor(Math.random() * overlayPhrases.length);
        phraseEl.textContent = overlayPhrases[currentIdx];

        const intervalId = window.setInterval(() => {
            let nextIdx;

            // 2. 바로 직전에 나온 문구가 또 나오지 않도록 뽑기 (배열이 2개 이상일 때만 유효)
            do {
                nextIdx = Math.floor(Math.random() * overlayPhrases.length);
            } while (nextIdx === currentIdx && overlayPhrases.length > 1);

            currentIdx = nextIdx;
            phraseEl.textContent = overlayPhrases[currentIdx];
        }, 5000); // 4초마다 변경

        const setProgress = (loaded, total) => {
            if (!progressBar || !percentEl || !bytesEl) return;
            const safeTotal = total || file.size || 1;
            const percent = Math.min(100, Math.round((loaded / safeTotal) * 100));
            progressBar.style.width = `${percent}%`;
            percentEl.textContent = `${percent}%`;
            bytesEl.textContent = `${formatSize(loaded)} / ${formatSize(safeTotal)}`;
        };

        const markCompleted = () => {
            if (titleEl) {
                titleEl.textContent = "전송 완료! 분석을 시작합니다.";
                titleEl.style.color = "var(--primary-color)";
            }
            if (warningEl) {
                // 완료되면 경고 문구를 안내 문구로 부드럽게 변경하거나 숨김
                warningEl.innerHTML = "잠시 후 대시보드로 이동합니다...";
                warningEl.style.color = "#64748b"; // 회색으로 변경
                warningEl.style.fontWeight = "normal";
            }
            if (phraseEl) {
                phraseEl.textContent = ""; // 밈 문구 제거 혹은 유지
            }
            if (spinner) {
                spinner.style.borderTopColor = "#16a34a";
                spinner.style.borderRightColor = "#16a34a";
                spinner.style.borderBottomColor = "#16a34a";
                spinner.style.borderLeftColor = "#16a34a";
                spinner.style.animation = "none";
            }
        };

        const destroy = () => {
            window.clearInterval(intervalId);
            overlay.remove();
        };

        return { setProgress, markCompleted, destroy };
    };

    const uploadToS3WithProgress = (file, url, fields, overlayCtrl) => {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            Object.entries(fields).forEach(([key, value]) => {
                formData.append(key, value);
            });
            formData.append("file", file);

            const xhr = new XMLHttpRequest();
            xhr.open("POST", url, true);

            xhr.upload.addEventListener("progress", (event) => {
                if (event.lengthComputable && overlayCtrl) {
                    overlayCtrl.setProgress(event.loaded, event.total);
                }
            });

            xhr.onreadystatechange = () => {
                if (xhr.readyState !== XMLHttpRequest.DONE) return;

                if (xhr.status >= 200 && xhr.status < 300) {
                    if (overlayCtrl) {
                        overlayCtrl.setProgress(file.size, file.size);
                    }
                    resolve();
                } else {
                    reject(new Error("S3 upload failed"));
                }
            };

            xhr.onerror = () => {
                reject(new Error("S3 upload error"));
            };

            xhr.send(formData);
        });
    };

    const startUploadFlow = async () => {
        if (!zipInput.files || zipInput.files.length === 0 || !currentFile) {
            alert("먼저 ZIP 파일을 선택해주세요.");
            return;
        }

        // presign/register URL이 아직 세팅 안 된 경우 → 기존 폼 제출로 폴백
        if (!presignUrl || !registerUrl) {
            form.submit();
            return;
        }

        const file = currentFile;
        const expectedPoints = currentImageCount * 2;

        browseBtn.disabled = true;
        resetBtn.disabled = true;
        analyzeBtn.disabled = true;

        const overlayCtrl = createUploadOverlay(file);

        try {
            const presignResp = await fetch(presignUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    filename: file.name,
                    size_bytes: file.size,
                    image_count: currentImageCount,
                    expected_points: expectedPoints,
                }),
            });

            if (!presignResp.ok) {
                throw new Error("Failed to create presigned URL");
            }

            const presignData = await presignResp.json();
            const jobId = presignData.job_id;
            const uploadInfo = presignData.upload || presignData.post;

            if (!jobId || !uploadInfo || !uploadInfo.url || !uploadInfo.fields) {
                throw new Error("Invalid presign response");
            }

            await uploadToS3WithProgress(file, uploadInfo.url, uploadInfo.fields, overlayCtrl);

            const registerResp = await fetch(registerUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({ job_id: jobId }),
            });

            if (!registerResp.ok) {
                throw new Error("Failed to register upload");
            }

            overlayCtrl.markCompleted();

            // 업로드 + 등록 완료 후 대시보드로 자동 이동
            setTimeout(() => {
                window.location.href = form.dataset.dashboardUrl;
            }, 2000);

        } catch (err) {
            console.error(err);
            overlayCtrl.destroy();
            browseBtn.disabled = false;
            resetBtn.disabled = false;
            analyzeBtn.disabled = false;
            alert("업로드 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
        }
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

    // 3. Submit / Analyze
    analyzeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        startUploadFlow();
    });
}
