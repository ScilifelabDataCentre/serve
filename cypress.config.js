const { defineConfig } = require("cypress");

module.exports = defineConfig({
  env: {
    //do_reset_db: false,
    wait_db_reset: 60000,
    create_resources: true,
    run_extended_k8s_checks: false,
    populate_test_data_management_views_secret: process.env.POPULATE_TEST_DATA_MANAGEMENT_VIEWS_SECRET,
    manage_test_data_via_django_endpoint_views: true
  },

  e2e: {
    baseUrl: 'https://serve-dev.scilifelab.se',

    // Exclude the integration tests from CI
    excludeSpecPattern: [
        "cypress/e2e/integration-tests/*"
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
