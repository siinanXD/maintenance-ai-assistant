(function () {
  "use strict";

  /**
   * Return visible focusable elements within a dialog container.
   *
   * @param {Element} container Dialog container.
   * @returns {HTMLElement[]} Focusable elements.
   */
  function focusableElements(container) {
    return Array.from(container.querySelectorAll(
      "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
    )).filter((element) => element.offsetParent !== null || element === document.activeElement);
  }

  /**
   * Ensure the reusable action dialog exists in the DOM.
   *
   * @returns {HTMLElement} Dialog overlay.
   */
  function ensureActionDialog() {
    let overlay = document.querySelector("[data-action-dialog]");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.className = "modal action-dialog";
    overlay.dataset.actionDialog = "true";
    overlay.hidden = true;
    overlay.innerHTML = [
      '<form class="modal-box action-dialog-box" data-action-dialog-form role="dialog" aria-modal="true" aria-labelledby="action-dialog-title" aria-describedby="action-dialog-message action-dialog-error">',
      '  <div class="panel-header action-dialog-header">',
      '    <div>',
      '      <p class="page-kicker" data-action-dialog-kicker>Aktion</p>',
      '      <h2 class="panel-title" id="action-dialog-title" data-action-dialog-title></h2>',
      '    </div>',
      '  </div>',
      '  <p class="panel-meta action-dialog-message" id="action-dialog-message" data-action-dialog-message></p>',
      '  <label class="field action-dialog-field" data-action-dialog-field>',
      '    <span data-action-dialog-label></span>',
      '    <input class="input input-bordered w-full" aria-describedby="action-dialog-error" data-action-dialog-input>',
      '    <textarea class="textarea textarea-bordered w-full" rows="4" aria-describedby="action-dialog-error" data-action-dialog-textarea></textarea>',
      '  </label>',
      '  <p class="form-message" id="action-dialog-error" data-action-dialog-error role="alert"></p>',
      '  <div class="toolbar action-dialog-actions">',
      '    <button class="btn btn-ghost" type="button" data-action-dialog-cancel>Abbrechen</button>',
      '    <button class="btn btn-primary" type="submit" data-action-dialog-confirm>OK</button>',
      '  </div>',
      '</form>'
    ].join("");
    document.body.appendChild(overlay);
    return overlay;
  }

  /**
   * Open the shared action dialog.
   *
   * @param {object} options Dialog options.
   * @returns {Promise<boolean|string|null>} Dialog result.
   */
  function openActionDialog(options) {
    const settings = options || {};
    const mode = settings.mode || "info";
    const overlay = ensureActionDialog();
    const dialog = overlay.querySelector("[data-action-dialog-form]");
    const title = overlay.querySelector("[data-action-dialog-title]");
    const kicker = overlay.querySelector("[data-action-dialog-kicker]");
    const message = overlay.querySelector("[data-action-dialog-message]");
    const field = overlay.querySelector("[data-action-dialog-field]");
    const label = overlay.querySelector("[data-action-dialog-label]");
    const input = overlay.querySelector("[data-action-dialog-input]");
    const textarea = overlay.querySelector("[data-action-dialog-textarea]");
    const error = overlay.querySelector("[data-action-dialog-error]");
    const cancelButton = overlay.querySelector("[data-action-dialog-cancel]");
    const confirmButton = overlay.querySelector("[data-action-dialog-confirm]");
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const usesText = mode === "text";
    const textControl = settings.multiline ? textarea : input;

    title.textContent = settings.title || "Aktion bestätigen";
    kicker.textContent = settings.kicker || (mode === "text" ? "Eingabe" : "Aktion");
    message.textContent = settings.message || "";
    label.textContent = settings.label || "Wert";
    error.textContent = "";
    error.classList.remove("is-error");
    field.hidden = !usesText;
    input.hidden = settings.multiline || !usesText;
    textarea.hidden = !settings.multiline || !usesText;
    input.value = settings.defaultValue || "";
    textarea.value = settings.defaultValue || "";
    input.removeAttribute("aria-invalid");
    textarea.removeAttribute("aria-invalid");
    input.type = settings.inputType || "text";
    input.required = Boolean(settings.required && !settings.multiline);
    textarea.required = Boolean(settings.required && settings.multiline);
    confirmButton.textContent = settings.confirmText || (mode === "confirm" ? "Bestätigen" : "OK");
    cancelButton.textContent = settings.cancelText || "Abbrechen";
    cancelButton.hidden = mode === "info";
    overlay.hidden = false;
    document.body.classList.add("has-open-dialog");

    return new Promise((resolve) => {
      let settled = false;

      function closeDialog(value) {
        if (settled) return;
        settled = true;
        overlay.hidden = true;
        document.body.classList.remove("has-open-dialog");
        dialog.removeEventListener("submit", handleSubmit);
        cancelButton.removeEventListener("click", handleCancel);
        overlay.removeEventListener("click", handleOverlayClick);
        overlay.removeEventListener("keydown", handleKeydown);
        if (previousFocus && previousFocus.focus) previousFocus.focus();
        resolve(value);
      }

      function handleCancel() {
        closeDialog(mode === "confirm" ? false : null);
      }

      function handleOverlayClick(event) {
        if (event.target === overlay) handleCancel();
      }

      function handleKeydown(event) {
        if (event.key === "Escape") {
          event.preventDefault();
          handleCancel();
          return;
        }
        if (event.key !== "Tab") return;
        const focusable = focusableElements(dialog);
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }

      function handleSubmit(event) {
        event.preventDefault();
        if (mode === "confirm" || mode === "info") {
          closeDialog(true);
          return;
        }
        const value = textControl.value || "";
        if (settings.required && !value.trim()) {
          error.textContent = settings.requiredMessage || "Bitte einen Wert eingeben.";
          error.classList.add("is-error");
          textControl.setAttribute("aria-invalid", "true");
          textControl.focus();
          return;
        }
        textControl.removeAttribute("aria-invalid");
        closeDialog(value);
      }

      dialog.addEventListener("submit", handleSubmit);
      cancelButton.addEventListener("click", handleCancel);
      overlay.addEventListener("click", handleOverlayClick);
      overlay.addEventListener("keydown", handleKeydown);
      window.setTimeout(() => {
        if (usesText) textControl.focus();
        else confirmButton.focus();
      }, 0);
    });
  }

  window.maintenanceDialogs = {
    confirmAction: (options) => openActionDialog({ ...(options || {}), mode: "confirm" }),
    requestText: (options) => openActionDialog({ ...(options || {}), mode: "text" })
  };
})();
