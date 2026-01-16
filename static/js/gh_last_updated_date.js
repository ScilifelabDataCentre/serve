function formatDate(date) {
  const yyyy = date.getUTCFullYear();
  const mm = String(date.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(date.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

async function init() {
  const container = document.querySelector("[data-gh-updated]");
  if (!container) return;

  const span = container.querySelector("[data-gh-path]");
  if (!span) return;

  const path = span.dataset.ghPath;
  if (!path) return;

  const url =
    `https://api.github.com/repos/scilifelabdatacentre/serve` +
    `/commits?sha=main&path=${encodeURIComponent(path)}&per_page=1`;

  try {
    const res = await fetch(url, {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!res.ok) return;

    const data = await res.json();
    if (!Array.isArray(data) || data.length === 0) return;

    const iso = data[0]?.commit?.committer?.date;
    if (!iso) return;

    span.textContent = formatDate(new Date(iso));
    container.hidden = false; // show the paragraph with last updated date only on success
  } catch {
    // keep it hidden on any error
  }
}

document.readyState === "loading"
  ? document.addEventListener("DOMContentLoaded", init)
  : init();
