const baseUrl = (process.env.STUDIO_URL || "http://studio.127.0.0.1.nip.io:8080").replace(/\/$/, "");
const username = process.env.A11Y_TEST_USERNAME || "no-reply-a11y@scilifelab.uu.se";
const password = process.env.A11Y_TEST_PASSWORD || "tesT12345@";

const publicPaths = [
  "/",
  "/apps/",
  "/models/",
  "/signup/",
  "/about/",
  "/about/roadmap/",
  "/about/cite/",
  "/contact/",
  "/privacy/",
  "/collections/",
  "/teaching/",
  "/news/",
  "/events/",
  "/accounts/login/",
  "/accounts/password_reset/",
  "/docs/",
  "/openapi/",
];

const loginActions = [
  `set field #username-id to ${username}`,
  `set field #password-id to ${password}`,
  'click element button[type="submit"]',
  "wait for path to be /projects/",
];

function absoluteUrl(path) {
  return new URL(path, `${baseUrl}/`).toString();
}

function authenticatedPath(path) {
  return {
    url: absoluteUrl("/accounts/login/"),
    actions: [
      ...loginActions,
      `navigate to ${absoluteUrl(path)}`,
      "wait for element body to be visible",
    ],
  };
}

function projectDetailAction() {
  return {
    url: absoluteUrl("/accounts/login/"),
    actions: [
      ...loginActions,
      "wait for element .card-footer a.btn-primary to be visible",
      "click element .card-footer a.btn-primary",
      "wait for element [data-cy=\"settings\"] to be visible",
    ],
  };
}

function projectSettingsAction() {
  return {
    url: absoluteUrl("/accounts/login/"),
    actions: [
      ...loginActions,
      "wait for element .card-footer a.btn-primary to be visible",
      "click element .card-footer a.btn-primary",
      "wait for element [data-cy=\"settings\"] to be visible",
      "click element [data-cy=\"settings\"]",
      "wait for element body to be visible",
    ],
  };
}

function appCreateAction(appSlug) {
  const selector = `a[href$="/apps/create/${appSlug}?from=overview"]`;

  return {
    url: absoluteUrl("/accounts/login/"),
    actions: [
      ...loginActions,
      "wait for element .card-footer a.btn-primary to be visible",
      "click element .card-footer a.btn-primary",
      `wait for element ${selector} to be visible`,
      `click element ${selector}`,
      "wait for element #submit-id-submit to be visible",
    ],
  };
}

module.exports = {
  defaults: {
    chromeLaunchConfig: {
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
      ignoreHTTPSErrors: true,
    },
    hideElements: "div.g-recaptcha, div.plot_wrapper, iframe[style*='display: none']",
    ignore: ["color-contrast"],
    reporters: [
      "cli",
      ["json", { fileName: "./pa11y-ci-report/results.json" }],
    ],
    runners: ["htmlcs", "axe"],
    standard: "WCAG2AA",
    timeout: 120000,
    wait: 1500,
  },
  urls: [
    ...publicPaths.map(absoluteUrl),
    authenticatedPath("/projects/"),
    authenticatedPath("/projects/templates/"),
    authenticatedPath("/projects/create/"),
    authenticatedPath("/edit-profile/"),
    projectDetailAction(),
    projectSettingsAction(),
    appCreateAction("jupyter-lab"),
    appCreateAction("filemanager"),
    appCreateAction("customapp"),
    appCreateAction("streamlit"),
    appCreateAction("dashapp"),
  ],
};
