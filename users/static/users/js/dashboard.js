function toggleDetails(id) {
    var element = document.getElementById(id);
    var arrow = element.previousElementSibling.querySelector('.arrow_bracket');

    if (element.classList.contains('open')) {
        element.classList.remove('open');
        arrow.style.transform = "rotate(0deg)"; // Restore original arrow position
    } else {
        element.classList.add('open');
        arrow.style.transform = "rotate(180deg)"; // Rotate arrow down
    }
}

function getCSRFToken() {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, 10) === "csrftoken=") {
                cookieValue = decodeURIComponent(cookie.substring(10));
                break;
            }
        }
    }
    return cookieValue;
}

function removeModal() {
    const existingModal = document.getElementById('deleteConfirmModal');
    if (existingModal) {
        existingModal.remove();
    }
}

function showDeleteModal(deleteBtn) {
    // Remove any old modal.
    removeModal();

    // Create modal element.
    const modal = document.createElement("div");
    modal.id = "deleteConfirmModal";
    modal.className = "modal";

    // Set inner HTML of modal.
    modal.innerHTML = `
      <div class="modal-content">
        <p class="modal-message">정말 삭제하시겠습니까?<br>이 작업은 되돌릴 수 없습니다.</p>
        <div class="modal-buttons">
          <button id="confirmDeleteButton" class="modal-button">예</button>
          <button id="cancelDeleteButton" class="modal-button">아니오</button>
        </div>
      </div>
    `;

    // Append modal to body.
    document.body.appendChild(modal);

    // Get the bounding rectangle of the delete button.
    const rect = deleteBtn.getBoundingClientRect();

    // Ensure modal is temporarily visible to measure its content.
    modal.style.display = "block";
    const modalContent = modal.querySelector(".modal-content");
    // Get modalContent dimensions.
    const modalRect = modal.getBoundingClientRect();

    const top = rect.top - modalRect.height - 8 + window.scrollY;
    const left = -3 + rect.left + (rect.width / 2) - (modalRect.width / 2) + window.scrollX;

    modal.style.top = top + 'px';
    modal.style.left = left + 'px';

    // Trigger the transition.
    setTimeout(() => {
        modal.classList.add("show");
    }, 10);

    // Attach a listener to dismiss the modal if click occurs outside modal-content.
    function outsideClickListener(e) {
        if (!modal.contains(e.target)) {
            removeModal();
            document.removeEventListener('click', outsideClickListener);
        }
    }
    document.addEventListener("click", outsideClickListener);

    // Get the confirm and cancel buttons.
    const confirmButton = document.getElementById('confirmDeleteButton');
    const cancelButton = document.getElementById('cancelDeleteButton');

    // Remove any previously attached event listeners to avoid duplicates.
    confirmButton.replaceWith(confirmButton.cloneNode(true));
    cancelButton.replaceWith(cancelButton.cloneNode(true));

    const newConfirmButton = document.getElementById('confirmDeleteButton');
    const newCancelButton = document.getElementById('cancelDeleteButton');

    // Attach confirm button event.
    newConfirmButton.addEventListener("click", function (e) {
        e.stopPropagation();
        const resultId = deleteBtn.getAttribute("data-result-id");
        fetch(`/delete_result/${resultId}/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": getCSRFToken(),
                "X-Requested-With": "XMLHttpRequest"
            }
        })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(errData => { throw errData; });
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    // alert("삭제되었습니다.");
                    location.reload();
                } else {
                    alert("삭제에 실패하였습니다.");
                }
            })
            .catch(err => {
                console.error("Deletion error:", err);
                alert("삭제 중 오류가 발생했습니다. 다시 시도해주세요.");
            });
        removeModal();
        document.removeEventListener("click", outsideClickListener);
    });

    // Attach cancel button event.
    newCancelButton.addEventListener("click", function (e) {
        e.stopPropagation();
        removeModal();
        document.removeEventListener("click", outsideClickListener);
    });
}




document.addEventListener("DOMContentLoaded", function () {
    const dateElement = document.getElementById("nickname-change-date");
    if (dateElement) {
        const utcDate = dateElement.getAttribute("data-date");
        if (utcDate) {
            const localDate = new Date(utcDate);

            // Format YYYY-MM-DD
            const year = localDate.getFullYear();
            const month = String(localDate.getMonth() + 1).padStart(2, '0');
            const day = String(localDate.getDate()).padStart(2, '0');
            const formattedDate = `${year}-${month}-${day}`;

            // Insert formatted local date
            dateElement.textContent = formattedDate;
        }
    }


    document.querySelectorAll(".date-container").forEach(container => {
        const utcDate = container.getAttribute("data-date");
        if (utcDate) {
            const localDate = new Date(utcDate);

            // Format YYYY-MM-DD
            const year = localDate.getFullYear();
            const month = String(localDate.getMonth() + 1).padStart(2, '0');
            const day = String(localDate.getDate()).padStart(2, '0');
            const formattedDate = `${year}-${month}-${day}`;

            // Format h:i A (12-hour format with AM/PM)
            let hours = localDate.getHours();
            const minutes = String(localDate.getMinutes()).padStart(2, '0');
            const ampm = hours >= 12 ? 'PM' : 'AM';
            hours = hours % 12 || 12; // Convert 24-hour to 12-hour format
            const formattedTime = `${hours}:${minutes} ${ampm}`;

            // Insert into HTML
            container.querySelector(".formatted-date").textContent = formattedDate;
            container.querySelector(".formatted-time").textContent = formattedTime;
        }
    });

    document.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const resultId = this.getAttribute('data-result-id');
            window.location.href = `/result_ocr/view/${resultId}/`;
        });
    });

    document.querySelectorAll('.calculation-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const resultId = this.getAttribute('data-result-id');
            window.location.href = `/calculate/${resultId}/`;
        });
    });

    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            showDeleteModal(this);
        });
    });


});

