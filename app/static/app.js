(function () {
  function toastVariantName(variant) {
    if (variant === "success" || variant === "error" || variant === "info") return variant;
    return "info";
  }

  function showInterfaceToast(message, options) {
    const settings = typeof options === "string" ? { variant: options } : (options || {});
    const variant = toastVariantName(settings.variant);
    let toast = document.querySelector("[data-interface-toast]");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "interface-toast";
      toast.dataset.interfaceToast = "true";
      toast.setAttribute("role", "status");
      toast.setAttribute("aria-live", "polite");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.remove("is-success", "is-error", "is-info");
    toast.classList.add("is-" + variant);
    toast.hidden = false;
    window.clearTimeout(showInterfaceToast.timeoutId);
    showInterfaceToast.timeoutId = window.setTimeout(() => {
      toast.hidden = true;
    }, settings.duration || 3200);

    const liveRegion = document.querySelector("[data-global-live-region]");
    if (liveRegion) liveRegion.textContent = message;
  }

  function initAccessibleForms() {
    const interactiveSelector = "input, select, textarea";

    function updateInvalidState(field, forceInvalid) {
      if (!(field instanceof HTMLElement) || !field.matches(interactiveSelector)) return;
      const invalid = forceInvalid || (field.dataset.touched === "true" && field.validity && !field.validity.valid);
      if (invalid) {
        field.setAttribute("aria-invalid", "true");
        return;
      }
      field.removeAttribute("aria-invalid");
    }

    document.addEventListener("invalid", (event) => {
      updateInvalidState(event.target, true);
      showInterfaceToast("Bitte markierte Pflichtfelder prüfen.");
    }, true);

    ["input", "change"].forEach((eventName) => {
      document.addEventListener(eventName, (event) => {
        if (!(event.target instanceof HTMLElement)) return;
        event.target.dataset.touched = "true";
        updateInvalidState(event.target, false);
      });
    });
  }

  function tableCaptionText(table) {
    const context = table.closest("section, article, .panel, .app-card, .table-wrap");
    const heading = context
      ? context.querySelector("h1, h2, h3, h4, [data-table-caption]")
      : null;
    const headingText = heading ? heading.textContent.trim() : "";
    return headingText || "Datentabelle";
  }

  function prepareAccessibleTable(table) {
    if (!(table instanceof HTMLTableElement)) return;
    if (!table.querySelector("caption")) {
      const caption = document.createElement("caption");
      caption.className = "sr-only";
      caption.textContent = tableCaptionText(table);
      table.prepend(caption);
    }
    table.querySelectorAll("thead th:not([scope])").forEach((header) => {
      header.setAttribute("scope", "col");
    });
  }

  function initAccessibleTables() {
    const prepareAll = (root) => {
      root.querySelectorAll("table").forEach(prepareAccessibleTable);
    };
    prepareAll(document);
    new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (!(node instanceof HTMLElement)) return;
          if (node.matches("table")) prepareAccessibleTable(node);
          prepareAll(node);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  window.maintenanceFrontend = { showInterfaceToast };

  function boot() {
    initAccessibleForms();
    initAccessibleTables();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
