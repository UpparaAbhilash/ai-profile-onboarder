// Ask before submitting any form that has a data-confirm="..." attribute.
// Replaces inline onsubmit="..." handlers, which the Content Security Policy blocks.
document.addEventListener("submit", (event) => {
    const message = event.target.dataset.confirm;
    if (message && !window.confirm(message)) {
        event.preventDefault();
    }
});