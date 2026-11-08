// Small UI helpers. No inline JavaScript anywhere: the Content Security Policy blocks it.

// 1) Buttons with data-loading-text: disable after submit and show a loading label.
//    Prevents double submits (e.g. uploading the same resume twice by double-clicking).
document.addEventListener("submit", (event) => {
    if (event.defaultPrevented) {
        return; // e.g. the user clicked "Cancel" in a data-confirm dialog
    }
    const button = event.target.querySelector("button[data-loading-text]");
    if (!button) {
        return;
    }
    button.dataset.originalText = button.textContent;
    button.textContent = button.dataset.loadingText;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
});

// The browser's Back button can restore a page with the button still disabled.
window.addEventListener("pageshow", () => {
    document.querySelectorAll("button[data-original-text]").forEach((button) => {
        button.textContent = button.dataset.originalText;
        button.disabled = false;
        button.removeAttribute("aria-busy");
    });
});

// 2) File inputs with data-max-mb: show the chosen file and warn early about
//    wrong type or size. The server still validates everything.
document.querySelectorAll("input[type=file][data-max-mb]").forEach((input) => {
    const info = document.getElementById(input.dataset.infoId);
    input.addEventListener("change", () => {
        const file = input.files[0];
        if (!file || !info) {
            return;
        }
        const sizeMb = file.size / (1024 * 1024);
        const maxMb = Number(input.dataset.maxMb);
        let problem = "";
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            problem = "Please choose a PDF file.";
        } else if (sizeMb > maxMb) {
            problem = `This file is larger than ${maxMb} MB.`;
        }
        info.textContent = `${file.name} · ${sizeMb.toFixed(1)} MB` + (problem ? ` · ${problem}` : "");
        info.classList.toggle("text-danger", Boolean(problem));
        input.setAttribute("aria-invalid", problem ? "true" : "false");
    });
});