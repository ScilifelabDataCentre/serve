(() => {
  function setReadonly(messageTextarea, readonly) {
    if (!messageTextarea) return;

    // Keep value submitted (readonly), but prevent editing.
    messageTextarea.readOnly = readonly;
    messageTextarea.setAttribute("aria-disabled", readonly ? "true" : "false");

    const row = messageTextarea.closest(".form-row") || messageTextarea.closest(".field-message");
    if (!row) return;

    // django-prose-editor renders a ProseMirror editable surface.
    const proseMirror = row.querySelector(".ProseMirror");
    if (proseMirror) {
      proseMirror.setAttribute("contenteditable", readonly ? "false" : "true");
      proseMirror.style.pointerEvents = readonly ? "none" : "";
      proseMirror.style.opacity = readonly ? "0.6" : "";
    }

    // Show/hide a small hint.
    let hint = row.querySelector("#message-disabled-hint");
    if (!hint) {
      hint = document.createElement("p");
      hint.id = "message-disabled-hint";
      hint.className = "help";
      hint.style.marginTop = "6px";
      hint.textContent = "Message editing is disabled because a template is selected (template overrides message).";
      row.appendChild(hint);
    }
    hint.style.display = readonly ? "" : "none";
  }

  function sync() {
    const templateSelect = document.getElementById("id_template");
    const messageTextarea = document.getElementById("id_message");
    if (!templateSelect || !messageTextarea) return;

    const hasTemplate = Boolean(templateSelect.value);
    setReadonly(messageTextarea, hasTemplate);
  }

  window.addEventListener("load", () => {
    sync();

    const templateSelect = document.getElementById("id_template");
    if (templateSelect) {
      templateSelect.addEventListener("change", sync);
    }

    // Prose editor may initialize after load; re-apply once.
    setTimeout(sync, 250);
    setTimeout(sync, 1000);
  });
})();
