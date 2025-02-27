const { defineConfig } = require("cypress");

module.exports = defineConfig({
  env: {
    do_reset_db: false,
    wait_db_reset: 60000,
    create_resources: true,
    run_extended_k8s_checks: false,
  },

  e2e: {
    baseUrl: 'http://studio.127.0.0.1.nip.io:8080',
    //baseUrl: 'https://serve-dev.scilifelab.se',

    // Exclude the integration tests from CI
    // TODO: After app status refactor is done, the test-deploy-app.cy.js will be removed.
    excludeSpecPattern: [
        "cypress/e2e/integration-tests/*",
        "cypress/e2e/ui-tests/test-deploy-app.cy.js"
    ],

    setupNodeEvents(on, config) {
      // implement node event listeners here
      const logOptions = {
        printLogsToConsole: 'always',
      };

      require('cypress-terminal-report/src/installLogsPrinter')(on, logOptions);
    },
  },
});
