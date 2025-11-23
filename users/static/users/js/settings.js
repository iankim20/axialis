document.addEventListener('DOMContentLoaded', function () {

    const form = document.getElementById('settings-form');
    const messageDiv = document.getElementById('settings-message');
    const surgeonNameInput = document.getElementById('surgeonName');
    const actualSurgeonValue = surgeonNameInput.getAttribute('data-surgeon');

    function blinkMessage(ele) {
        ele.classList.add('blink');
        setTimeout(() => {
            ele.classList.remove('blink');
        }, 500);
    }

    if (!actualSurgeonValue || actualSurgeonValue.trim() === "" || actualSurgeonValue == "None") {
        // Automatically trigger a one-time AJAX POST request to update settings.
        const formData = new FormData(form);

        fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(response => {
                if (!response.ok) {
                    return response.json().then(errData => { throw errData; });
                }
                return response.json();
            })
            .then(data => {
                console.log("One-time Auto update success:", data);
                // messageDiv.textContent = "Settings auto-updated.";
                // messageDiv.style.color = "green";
            })
            .catch(errorData => {
                console.error("One-time Auto update error:", errorData);
                // messageDiv.textContent = "Auto update error: " + JSON.stringify(errorData.errors);
                // messageDiv.style.color = "red";
            });
    }



    form.addEventListener('submit', function (e) {
        // Check the visible value; if trimmed value is empty, alert and cancel submission.
        if (surgeonNameInput.value.trim() === "") {
            alert("수술 의사명은 빈 칸일 수 없습니다. \nSurgeon Name을 입력하세요.");
            e.preventDefault();
            return;
        }

        e.preventDefault();
        const formData = new FormData(form);

        fetch(form.action, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
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
                    messageDiv.textContent = data.message;
                    messageDiv.style.color = 'green';
                    blinkMessage(messageDiv); // revised: blink effect on success
                }
            })
            .catch(errorData => {
                messageDiv.textContent = 'Error: ' + JSON.stringify(errorData.errors);
                messageDiv.style.color = 'red';
                blinkMessage(messageDiv); // blink effect on error too

            });
    });


    /* Nickname Inline Editing Logic */
    // Instead of a modal, we show an inline div below the nickname field.
    const editNicknameBtn = document.getElementById('edit-nickname-btn');
    const pencil = document.getElementById('pencil');
    const nicknameEditDiv = document.getElementById('nickname-edit-div');
    const dupCheckBtn = document.getElementById('dup-check-btn');
    const saveNicknameBtn = document.getElementById('save-nickname-btn');
    const newNicknameInput = document.getElementById('new-nickname');
    const nicknameMessage = document.getElementById('nickname-message');
    const nicknameMessage2 = document.getElementById('nickname-message2');
    const nicknameDisplay = document.getElementById('nickname');
    // Get last nickname change date (as Unix timestamp) from the data attribute on nickname display
    const lastChangeTimestamp_raw = nicknameDisplay.getAttribute('data-last-change') || "";
    const lastChangeTimestamp = new Date(lastChangeTimestamp_raw).getTime() / 1000; // ✅ Convert to UNIX timestamp (seconds)

    const nowTimestamp = (Date.now() / 1000);
    const daysSinceChange = (nowTimestamp - lastChangeTimestamp) / (60 * 60 * 24);
    console.log(nowTimestamp, lastChangeTimestamp_raw, lastChangeTimestamp, daysSinceChange)

    const dateDescription = document.getElementById('date_description');

    editNicknameBtn.addEventListener('click', function () {
        if (daysSinceChange < 100) {
            // Conventional alert popup for this condition
            alert("닉네임은 100일마다 변경 가능합니다. 남은 일수: " + Math.ceil(100 - daysSinceChange));
            return;
        }
        else {
            if (nicknameEditDiv.style.display === "flex") {
                nicknameEditDiv.style.display = "none";
                pencil.classList.toggle("open");
            }
            else if (nicknameEditDiv.style.display === "none") {
                nicknameEditDiv.style.display = "flex";
                pencil.classList.toggle("open");
            }
        }
    });

    dupCheckBtn.addEventListener('click', function () {
        const newNick = newNicknameInput.value.trim();
        if (!newNick) {
            nicknameMessage.textContent = "새 닉네임을 입력하세요.";
            nicknameMessage.style.color = "red";
            blinkMessage(nicknameMessage)
            return;
        }
        fetch(checkNicknameURL + "?nickname=" + encodeURIComponent(newNick), {
            method: "GET",
            headers: {
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
                    nicknameMessage.textContent = data.message;
                    nicknameMessage.style.color = "green";
                    blinkMessage(nicknameMessage)
                } else {
                    nicknameMessage.textContent = data.error;
                    nicknameMessage.style.color = "red";
                    blinkMessage(nicknameMessage)
                }
            })
            .catch(errorData => {
                nicknameMessage.textContent = errorData.error;
                nicknameMessage.style.color = "red";
                blinkMessage(nicknameMessage)
            });
    });

    newNicknameInput.addEventListener('input', function () {
        nicknameMessage.textContent = "";
    });

    // --- Revised Save New Nickname AJAX call ---
    saveNicknameBtn.addEventListener('click', function () {
        const newNick = newNicknameInput.value.trim();
        if (!newNick) {
            nicknameMessage.textContent = "새 닉네임을 입력하세요.";
            nicknameMessage.style.color = "red";
            blinkMessage(nicknameMessage)
            return;
        }
        if (nicknameMessage.textContent !== "사용 가능한 닉네임입니다.") {
            alert("닉네임 중복 확인을 해주세요.");
            return;
        }
        const formData = new FormData();
        formData.append("nickname", newNick);
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
        fetch(updateNicknameURL, {  // NEW endpoint for nickname update
            method: "POST",
            body: formData,
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": csrfToken
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
                    nicknameDisplay.textContent = data.nickname;
                    const updated_date_raw = data.nickname_change_date
                    nicknameDisplay.setAttribute("data-last-change", updated_date_raw); // update last change timestamp

                    const localDate = new Date(updated_date_raw);

                    // Format YYYY-MM-DD
                    const year = localDate.getFullYear();
                    const month = String(localDate.getMonth() + 1).padStart(2, '0');
                    const day = String(localDate.getDate()).padStart(2, '0');
                    const formattedDate = `${year}-${month}-${day}`;

                    dateDescription.textContent = `닉네임(필명)은 100일마다 변경 가능합니다 (마지막 변경일: ${formattedDate}).`;


                    nicknameEditDiv.style.display = "none";
                    pencil.classList.toggle("open");
                    editNicknameBtn.disabled = true; // disable the button

                    nicknameMessage2.style.display = "flex"
                    nicknameMessage2.textContent = "닉네임이 성공적으로 변경되었습니다";
                    nicknameMessage2.style.color = "green";
                    blinkMessage(nicknameMessage2)


                }
            })
            .catch(errorData => {
                nicknameMessage.textContent = errorData.error;
                nicknameMessage.style.color = "red";
                blinkMessage(nicknameMessage)
            });
    });
});
