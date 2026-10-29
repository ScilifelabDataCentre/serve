function initializeEnvironmentEditors() {
  document.querySelectorAll("[data-environment-editor]").forEach(editor => {
    if (editor.dataset.initialized) return;
    editor.dataset.initialized = "true";

    const rows = editor.querySelector("[data-environment-config-rows]");
    const template = editor.querySelector("[data-environment-config-template]");
    const addButton = editor.querySelector("[data-environment-add-config]");

    function controls(row) {
      return [row.querySelector("input"), row.querySelector("textarea")];
    }

    function clearError(row) {
      const feedback = row.querySelector("[data-environment-name-error]");
      feedback.textContent = "";
      feedback.hidden = true;
      const name = controls(row)[0];
      name.classList.remove("is-invalid");
      name.removeAttribute("aria-invalid");
    }

    function showError(row, message) {
      clearError(row);
      const feedback = row.querySelector("[data-environment-name-error]");
      feedback.textContent = message;
      feedback.hidden = false;
      const name = controls(row)[0];
      name.classList.add("is-invalid");
      name.setAttribute("aria-invalid", "true");
      name.focus();
    }

    function resizeValue(textarea) {
      const nameHeight = textarea.closest("[data-environment-row-item]").querySelector("input").offsetHeight;
      textarea.style.height = `${nameHeight}px`;
      const contentHeight = textarea.scrollHeight + textarea.offsetHeight - textarea.clientHeight;
      if (contentHeight > nameHeight + 2) textarea.style.height = `${contentHeight}px`;
      textarea.style.overflowY = contentHeight > textarea.offsetHeight ? "auto" : "hidden";
    }

    function showSummary(row) {
      clearError(row);
      const [name, value] = controls(row);
      name.value = name.value.trim();
      row.querySelector("[data-environment-summary-name]").textContent = name.value;
      row.querySelector("[data-environment-summary-detail]").textContent = value.value || "(empty value)";
      const summary = row.querySelector("[data-environment-summary]");
      summary.classList.add("d-flex");
      summary.hidden = false;
      row.querySelector("[data-environment-fields]").hidden = true;
      row.querySelector("[data-environment-done]").hidden = true;
      row.querySelector("[data-environment-remove-edit]").hidden = true;
    }

    function showEditor(row) {
      clearError(row);
      const summary = row.querySelector("[data-environment-summary]");
      summary.classList.remove("d-flex");
      summary.hidden = true;
      row.querySelector("[data-environment-fields]").hidden = false;
      row.querySelector("[data-environment-done]").hidden = false;
      row.querySelector("[data-environment-remove-edit]").hidden = false;
      resizeValue(controls(row)[1]);
      controls(row)[0].focus();
    }

    function rowError(row) {
      const name = controls(row)[0].value.trim();
      if (!name) return "Enter a variable name.";
      if (!/^[A-Za-z_][A-Za-z0-9_]{0,252}$/.test(name)) {
        return "Variable names must start with a letter or underscore and contain only letters, digits, or underscores.";
      }
      if (Array.from(rows.children).some(other => other !== row && controls(other)[0].value.trim() === name)) {
        return "Use a unique variable name.";
      }
      return "";
    }

    function validRow(row) {
      const message = rowError(row);
      if (message) {
        showError(row, message);
        return false;
      }
      clearError(row);
      return true;
    }

    addButton.hidden = false;
    addButton.addEventListener("click", () => {
      const row = template.content.firstElementChild.cloneNode(true);
      rows.append(row);
      showEditor(row);
    });

    for (const row of Array.from(rows.children)) {
      const [name, value] = controls(row);
      if (!name.value.trim() && !value.value) row.remove();
      else {
        const message = rowError(row);
        if (message) {
          showEditor(row);
          showError(row, message);
        } else showSummary(row);
      }
    }

    rows.addEventListener("input", event => {
      const row = event.target.closest("[data-environment-row-item]");
      if (event.target.matches("input")) clearError(row);
      if (event.target.matches("textarea")) resizeValue(event.target);
    });

    rows.addEventListener("click", event => {
      const row = event.target.closest("[data-environment-row-item]");
      if (!row) return;
      if (event.target.closest("[data-environment-edit]")) showEditor(row);
      else if (event.target.closest("[data-environment-remove], [data-environment-remove-edit]")) row.remove();
      else if (event.target.closest("[data-environment-done]") && validRow(row)) showSummary(row);
    });

    const secretEditor = editor.closest("form")?.querySelector("[data-environment-secret-editor]");
    if (!secretEditor) return;

    const addSecret = editor.querySelector("[data-environment-add-secret]");
    const secretRows = secretEditor.querySelector("[data-environment-secret-rows]");
    addSecret.hidden = false;
    if (!secretRows) {
      addSecret.disabled = true;
      return;
    }
    const secretTemplate = secretEditor.querySelector("[data-environment-secret-template]");

    function updateSecretChoices() {
      const active = Array.from(secretRows.querySelectorAll("[data-environment-secret-name]"))
        .map(input => input.value).filter(Boolean);
      secretRows.querySelectorAll("[data-environment-secret-row]").forEach(row => {
        const selected = row.querySelector("[data-environment-secret-name]").value;
        row.querySelectorAll("[data-environment-secret-option]").forEach(option => {
          const name = option.dataset.environmentSecretOption;
          option.disabled = Boolean(name !== selected && active.includes(name));
          if (name === selected) option.setAttribute("aria-current", "true");
          else option.removeAttribute("aria-current");
        });
      });
      const total = secretTemplate.content.querySelectorAll("[data-environment-secret-option]").length;
      const rowCount = secretRows.querySelectorAll("[data-environment-secret-row]").length;
      addSecret.disabled = rowCount >= total;
    }

    function secretSelection(row) {
      const selected = row.querySelector("[data-environment-secret-name]").value;
      const options = Array.from(row.querySelectorAll("[data-environment-secret-options]"))
        .find(item => item.dataset.environmentSecretOptions === selected);
      return {
        all: Boolean(options?.querySelector("[data-environment-select-all]").checked),
        keys: Array.from(options?.querySelectorAll("[data-environment-secret-key]:checked") || [])
          .map(key => key.nextElementSibling.textContent.trim()),
      };
    }

    function updateSecretSummary(row) {
      const selected = row.querySelector("[data-environment-secret-name]").value;
      const button = row.querySelector("[data-environment-secret-value]");
      const summary = row.querySelector("[data-environment-secret-summary]");
      const { all, keys } = secretSelection(row);
      button.disabled = !selected;
      summary.textContent = all ? "All keys" :
        keys.length ? `${keys.length} ${keys.length === 1 ? "key" : "keys"} selected` : "Select keys";
      button.setAttribute("aria-label", `Secret keys: ${summary.textContent}`);
    }

    function clearSecretError(row) {
      const error = row.querySelector("[data-environment-secret-error]");
      error.textContent = "";
      error.hidden = true;
      const button = row.querySelector("[data-environment-secret-name-button]");
      button.classList.remove("is-invalid");
      button.removeAttribute("aria-invalid");
    }

    function showSecretEditor(row) {
      clearSecretError(row);
      const display = row.querySelector("[data-environment-secret-display]");
      display.classList.remove("d-flex");
      display.hidden = true;
      row.querySelector("[data-environment-secret-fields]").hidden = false;
      row.querySelector("[data-environment-confirm-secret]").hidden = false;
      row.querySelector("[data-environment-secret-name-button]").focus();
    }

    function showSecretDisplay(row) {
      clearSecretError(row);
      updateSecretSummary(row);
      row.querySelector("[data-environment-secret-display-name]").textContent =
        row.querySelector("[data-environment-secret-name]").value;
      const { all, keys } = secretSelection(row);
      row.querySelector("[data-environment-secret-display-value]").textContent =
        all ? "All keys" : keys.join(", ") || "Select keys";
      const display = row.querySelector("[data-environment-secret-display]");
      display.classList.add("d-flex");
      display.hidden = false;
      row.querySelector("[data-environment-secret-fields]").hidden = true;
      row.querySelector("[data-environment-confirm-secret]").hidden = true;
    }

    function validSecretRow(row) {
      const name = row.querySelector("[data-environment-secret-name]").value;
      if (name && row.querySelector("[data-environment-secret-options]:not([hidden]) input:checked")) return true;
      const error = row.querySelector("[data-environment-secret-error]");
      error.textContent = name ? "Select at least one key." : "Select a Secret.";
      error.hidden = false;
      const button = row.querySelector("[data-environment-secret-name-button]");
      button.classList.add("is-invalid");
      button.setAttribute("aria-invalid", "true");
      button.focus();
      return false;
    }

    function showSecretOptions(row, selectAll = false) {
      const selected = row.querySelector("[data-environment-secret-name]").value;
      const nameButton = row.querySelector("[data-environment-secret-name-button]");
      row.querySelector("[data-environment-secret-name-summary]").textContent = selected || "Select a Secret";
      nameButton.setAttribute("aria-label", `Kubernetes Secret: ${selected || "Select a Secret"}`);
      row.querySelectorAll("[data-environment-secret-options]").forEach(options => {
        const visible = options.dataset.environmentSecretOptions === selected;
        options.hidden = !visible;
        if (!visible) options.querySelectorAll("input").forEach(input => { input.checked = false; });
        else if (selectAll) options.querySelector("[data-environment-select-all]").checked = true;
      });
      updateSecretSummary(row);
      updateSecretChoices();
      clearSecretError(row);
    }

    addSecret.addEventListener("click", () => {
      if (addSecret.disabled) return;
      const row = secretTemplate.content.firstElementChild.cloneNode(true);
      secretRows.append(row);
      updateSecretChoices();
      showSecretEditor(row);
    });
    secretRows.querySelectorAll("[data-environment-secret-row]").forEach(row => {
      showSecretOptions(row);
      if (row.querySelector("[data-environment-secret-name]").value) showSecretDisplay(row);
      else showSecretEditor(row);
    });
    secretRows.addEventListener("change", event => {
      const row = event.target.closest("[data-environment-secret-row]");
      if (!row) return;
      if (event.target.matches("[data-environment-select-all], [data-environment-secret-key]")) {
        const options = event.target.closest("[data-environment-secret-options]");
        const all = options.querySelector("[data-environment-select-all]");
        const keys = Array.from(options.querySelectorAll("[data-environment-secret-key]"));
        if (event.target === all && all.checked) keys.forEach(key => { key.checked = false; });
        if (event.target !== all && event.target.checked) all.checked = false;
        if (!all.checked && !keys.some(key => key.checked)) all.checked = true;
      }
      updateSecretSummary(row);
    });
    secretRows.addEventListener("click", event => {
      const row = event.target.closest("[data-environment-secret-row]");
      if (!row) return;
      const choice = event.target.closest("[data-environment-secret-option]");
      if (choice) {
        const name = row.querySelector("[data-environment-secret-name]");
        const changed = name.value !== choice.dataset.environmentSecretOption;
        name.value = choice.dataset.environmentSecretOption;
        showSecretOptions(row, changed);
      } else if (event.target.closest("[data-environment-remove-secret]")) {
        row.remove();
        updateSecretChoices();
      } else if (event.target.closest("[data-environment-edit-secret]")) showSecretEditor(row);
      else if (event.target.closest("[data-environment-confirm-secret]") && validSecretRow(row)) {
        showSecretDisplay(row);
      }
    });
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeEnvironmentEditors);
} else {
  initializeEnvironmentEditors();
}
