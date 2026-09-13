(function () {
  const STATIC_VERSION = document.documentElement.dataset.staticVersion || "dev";
  window.maintenanceStaticVersion = STATIC_VERSION;
  const pageImportPromises = new Map();

  function onReady(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  }

  function normalizeSearchText(value) {
    return String(value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }

  function urlSearchValue() {
    const params = new URLSearchParams(window.location.search);
    return params.get("search") || "";
  }

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

  function setActionStatus(element, message, variant) {
    if (!element) return;
    const normalizedVariant = toastVariantName(variant);
    element.textContent = message || "";
    element.classList.remove("is-success", "is-error", "is-info");
    if (message) element.classList.add("is-" + normalizedVariant);
  }

  function setButtonBusy(button, busy, busyText) {
    if (!button) return;
    if (busy) {
      if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
      if (!button.dataset.originalDisabled) {
        button.dataset.originalDisabled = button.disabled ? "true" : "false";
      }
      button.disabled = true;
      button.classList.add("is-busy");
      button.setAttribute("aria-busy", "true");
      if (busyText) {
        button.dataset.busyText = busyText;
        button.textContent = busyText;
      }
      return;
    }
    button.classList.remove("is-busy");
    button.removeAttribute("aria-busy");
    button.disabled = button.dataset.originalDisabled === "true";
    if (button.dataset.originalText && (!button.dataset.busyText || button.textContent === button.dataset.busyText)) {
      button.textContent = button.dataset.originalText;
    }
    delete button.dataset.originalText;
    delete button.dataset.originalDisabled;
    delete button.dataset.busyText;
  }

  function setFormBusy(form, busy, busyText) {
    if (!form) return;
    const controls = Array.from(form.querySelectorAll("button, input, select, textarea"));
    form.classList.toggle("is-busy", Boolean(busy));
    form.setAttribute("aria-busy", String(Boolean(busy)));
    controls.forEach((control) => {
      if (control.matches("button[type='submit']")) {
        setButtonBusy(control, busy, busyText);
        return;
      }
      if (busy) {
        if (!control.dataset.originalDisabled) {
          control.dataset.originalDisabled = control.disabled ? "true" : "false";
        }
        control.disabled = true;
        return;
      }
      control.disabled = control.dataset.originalDisabled === "true";
      delete control.dataset.originalDisabled;
    });
    if (!busy) form.removeAttribute("aria-busy");
  }

  async function runAction(options) {
    const settings = options || {};
    const control = settings.button || settings.control || null;
    const form = settings.form || null;
    const statusElement = settings.statusElement || null;
    const busyText = settings.busyText || "Läuft...";
    if (control && control.disabled) return null;
    if (form) setFormBusy(form, true, busyText);
    else setButtonBusy(control, true, busyText);
    if (settings.pendingMessage) setActionStatus(statusElement, settings.pendingMessage, "info");
    try {
      const result = await settings.action();
      if (settings.successMessage) {
        setActionStatus(statusElement, settings.successMessage, "success");
        if (settings.toast !== false) showInterfaceToast(settings.successMessage, "success");
      }
      return result;
    } catch (error) {
      const message = error && error.message ? error.message : (settings.errorMessage || "Aktion fehlgeschlagen.");
      setActionStatus(statusElement, message, "error");
      showInterfaceToast(message, "error");
      if (settings.rethrow) throw error;
      return null;
    } finally {
      if (form) setFormBusy(form, false);
      else setButtonBusy(control, false);
    }
  }

  function workflowStatusElement() {
    const main = document.querySelector(".app-main");
    if (!main) return null;
    let status = main.querySelector("[data-workflow-status]");
    if (!status) {
      status = document.createElement("div");
      status.className = "workflow-status";
      status.dataset.workflowStatus = "true";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      main.prepend(status);
    }
    return status;
  }

  function setWorkflowStatus(message, variant) {
    const status = workflowStatusElement();
    if (!status) return;
    setActionStatus(status, message, variant || "info");
    status.hidden = !message;
  }

  function confirmAction(options) {
    return window.maintenanceDialogs.confirmAction(options);
  }

  function requestText(options) {
    return window.maintenanceDialogs.requestText(options);
  }

  function showInfoDialog(options) {
    return window.maintenanceDialogs.showInfoDialog(options);
  }

  function initLocalListSearch() {
    const searchInputs = Array.from(document.querySelectorAll("[data-list-search]"));
    searchInputs.forEach((input) => {
      const deepLinkSearch = urlSearchValue();
      if (deepLinkSearch && !input.value) input.value = deepLinkSearch;
      const targetSelector = input.dataset.listSearchTarget;
      if (!targetSelector) return;
      const target = document.querySelector(targetSelector);
      if (!target) return;

      const applyFilter = () => {
        const query = normalizeSearchText(input.value);
        const itemSelector = target.dataset.listSearchItems || (target.tagName === "TBODY" ? "tr" : ":scope > *");
        Array.from(target.querySelectorAll(itemSelector)).forEach((item) => {
          const isEmptyState = item.classList.contains("empty-state");
          const matches = !query || normalizeSearchText(item.textContent).includes(query);
          item.hidden = !isEmptyState && !matches;
        });
      };

      input.addEventListener("input", applyFilter);
      new MutationObserver(applyFilter).observe(target, { childList: true, subtree: true });
      applyFilter();
    });
  }

  function initDeepLinkedSearchInputs() {
    const deepLinkSearch = urlSearchValue();
    if (!deepLinkSearch) return;
    document.querySelectorAll("[data-error-search]").forEach((input) => {
      if (!input.value) input.value = deepLinkSearch;
    });
  }

  function initHelpDisclosures() {
    document.querySelectorAll(".help-disclosure").forEach((details) => {
      const summary = details.querySelector("summary");
      if (!summary) return;
      summary.setAttribute("aria-expanded", String(details.open));
      details.addEventListener("toggle", () => {
        summary.setAttribute("aria-expanded", String(details.open));
      });
    });
  }

  function initMobileCollapsibleSections() {
    const sections = Array.from(document.querySelectorAll("[data-mobile-collapsible]"));
    if (!sections.length || !window.matchMedia) return;

    const mobileQuery = window.matchMedia("(max-width: 639px)");
    let syncing = false;

    function syncSections() {
      syncing = true;
      sections.forEach((section) => {
        if (mobileQuery.matches) {
          if (!section.dataset.mobileTouched) section.open = false;
          return;
        }
        section.open = section.dataset.defaultCollapsed !== "true";
      });
      syncing = false;
    }

    sections.forEach((section) => {
      section.addEventListener("toggle", () => {
        if (syncing) return;
        if (mobileQuery.matches) section.dataset.mobileTouched = "true";
      });
    });

    syncSections();
    if (mobileQuery.addEventListener) {
      mobileQuery.addEventListener("change", syncSections);
    } else if (mobileQuery.addListener) {
      mobileQuery.addListener(syncSections);
    }
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

    document.addEventListener("input", (event) => {
      if (!(event.target instanceof HTMLElement)) return;
      event.target.dataset.touched = "true";
      updateInvalidState(event.target, false);
    });

    document.addEventListener("change", (event) => {
      if (!(event.target instanceof HTMLElement)) return;
      event.target.dataset.touched = "true";
      updateInvalidState(event.target, false);
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

  function pageModuleUrlForPath(pathname) {
    const featureRegistry = window.maintenanceFeatures;
    if (featureRegistry && featureRegistry.forPath) {
      const feature = featureRegistry.forPath(pathname);
      if (feature && feature.module === "page" && feature.moduleUrl) {
        return feature.moduleUrl + "?v=" + STATIC_VERSION;
      }
    }
    return null;
  }

  function pageModuleRequiresAuth(pathname) {
    if (pathname === "/login") return false;
    const featureRegistry = window.maintenanceFeatures;
    if (!featureRegistry || !featureRegistry.forPath) return true;
    return Boolean(featureRegistry.forPath(pathname));
  }

  function pageLoadErrorMessage(label, pathname) {
    return label + " für " + pathname + " konnte nicht geladen werden. Bitte Seite neu laden.";
  }

  function pageLoadToastMessage(label, pathname) {
    return label + " für " + pathname + " konnte nicht geladen werden.";
  }

  async function loadPageModule() {
    const moduleUrl = pageModuleUrlForPath(window.location.pathname);
    if (!moduleUrl) return null;
    if (pageModuleRequiresAuth(window.location.pathname) && (!window.maintenanceAuth || !window.maintenanceAuth.token())) {
      setWorkflowStatus("Sitzung wird geladen. Aktionen werden gleich aktiviert.", "info");
      return null;
    }
    if (!pageImportPromises.has(moduleUrl)) {
      setWorkflowStatus("Seitendaten werden geladen...", "info");
      pageImportPromises.set(moduleUrl, import(moduleUrl).catch((error) => {
        pageImportPromises.delete(moduleUrl);
        setWorkflowStatus(pageLoadErrorMessage("Seitenmodul", window.location.pathname), "error");
        console.warn("page_module_load_failed", {
          route: window.location.pathname,
          moduleUrl,
          error
        });
        showInterfaceToast(pageLoadToastMessage("Seitenmodul", window.location.pathname), "error");
        throw error;
      }));
    }
    const module = await pageImportPromises.get(moduleUrl);
    setWorkflowStatus("", "info");
    return module;
  }

  async function boot() {
    initMobileCollapsibleSections();
    initDeepLinkedSearchInputs();
    initLocalListSearch();
    initHelpDisclosures();
    initAccessibleForms();
    initAccessibleTables();

    try {
      if (window.maintenanceAuth && window.maintenanceAuth.ensureReady) {
        await window.maintenanceAuth.ensureReady();
      }
      await loadPageModule();
    } catch (error) {
      console.warn(error);
    }
  }

  window.maintenanceFrontend = {
    confirmAction,
    loadPageModule,
    requestText,
    runAction,
    setActionStatus,
    setButtonBusy,
    setFormBusy,
    setWorkflowStatus,
    showInfoDialog,
    showInterfaceToast
  };

  window.addEventListener("maintenance-auth-changed", () => {
    loadPageModule().catch((error) => console.warn(error));
  });

  onReady(boot);
})();
