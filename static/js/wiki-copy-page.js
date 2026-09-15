(function () {
  "use strict";

  const menu = document.querySelector("[data-copy-page-menu]");
  if (!menu) return;

  const copyButtons = menu.querySelectorAll("[data-copy-page-copy]");
  const primaryLabel = menu.querySelector("[data-copy-page-primary-label]");
  const menuLabel = menu.querySelector("[data-copy-page-menu-label]");
  // Id comes from the json_script filter at the bottom of article_menu.html.
  const source = document.getElementById("copy-page-markdown-source");

  const labels = {
    primary: primaryLabel ? primaryLabel.textContent : "",
    menu: menuLabel ? menuLabel.textContent : "",
  };
  let statusTimer = null;

  // Connect the chatbot links first: they only need the URL, so a missing or empty
  // revision must not take them down with it.
  setChatbotLinks(buildPrompt(absoluteUrl(menu.dataset.sourceUrl)));

  if (source) {
    copyButtons.forEach(function (button) {
      button.addEventListener("click", async function () {
        try {
          await copyText(getPageMarkdown());
          showStatus(menu.dataset.copiedLabel || "Copied!");
        } catch (error) {
          console.error("Unable to copy wiki page as Markdown", error);
          showStatus(menu.dataset.copyFailedLabel || "Copy failed");
        }
      });
    });
  } else {
    // Nothing to put on the clipboard.
    copyButtons.forEach(function (button) {
      button.disabled = true;
    });
  }

  function absoluteUrl(path) {
    // django-wiki serves the raw Markdown at /<path>/_source/. It has no ".md"
    // route, so building one by suffixing the article path always gave a 404 and
    // the chatbot had nothing to read.
    const base = path || window.location.pathname;
    const url = new URL(base, window.location.href);
    url.search = "";
    url.hash = "";
    return url.toString();
  }

  function buildPrompt(url) {
    const template =
      menu.dataset.llmPrompt || "Read from {url} so I can ask questions about it.";
    const extra =
      menu.dataset.llmExtraPrompt ||
      "For additional information or guidance on creating apps, also refer to https://github.com/ScilifelabDataCentre/serve-app-template.";

    return `${template.replace("{url}", url)}\n\n${extra}`;
  }

  function setChatbotLinks(prompt) {
    const q = encodeURIComponent(prompt);
    const links = {
      // SciLifeLab Open LLM runs Open WebUI, where q starts a new chat with
      // the supplied prompt.
      openllm: `https://open-llm.scilifelab.se/?q=${q}`,
      // hints=search puts ChatGPT in browsing mode so it fetches the URL rather
      // than answering from memory.
      chatgpt: `https://chatgpt.com/?hints=search&q=${q}`,
      claude: `https://claude.ai/new?q=${q}`,
    };

    menu.querySelectorAll("[data-copy-page-chatbot]").forEach(function (link) {
      const href = links[link.dataset.copyPageChatbot];
      if (href) link.href = href;
    });
  }

  function getPageMarkdown() {
    // json_script serialises an article with no revision content as null, which
    // has no .trim(), so coerce before touching it.
    const parsed = JSON.parse(source.textContent || '""');
    const markdown = (typeof parsed === "string" ? parsed : "").trim();
    const title = (menu.dataset.articleTitle || "").trim();

    if (!title || markdown.startsWith(`# ${title}`)) return markdown;
    return `# ${title}\n\n${markdown}`.trim();
  }

  async function copyText(text) {
    if (!text) throw new Error("There is no Markdown to copy");

    if (!navigator.clipboard || !window.isSecureContext) {
      throw new Error("Clipboard API is unavailable outside a secure context");
    }

    await navigator.clipboard.writeText(text);
  }

  function showStatus(message) {
    if (primaryLabel) primaryLabel.textContent = message;
    if (menuLabel) menuLabel.textContent = message;

    // Rapid clicks used to stack timers, so an early one reset a later message.
    window.clearTimeout(statusTimer);
    statusTimer = window.setTimeout(function () {
      if (primaryLabel) primaryLabel.textContent = labels.primary;
      if (menuLabel) menuLabel.textContent = labels.menu;
    }, 1400);
  }
})();
