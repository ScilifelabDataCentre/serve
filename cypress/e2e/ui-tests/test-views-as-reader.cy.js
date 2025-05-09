describe("Test views as authenticated user", () => {

  // Tests performed as an authenticated user that only reads views
  // user: e2e_tests_login_tester

  let users
  let TEST_USER_DATA

  before(() => {
    cy.logf("Begin before() hook", Cypress.currentTest)

    if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
      cy.log("Populating test data via Django endpoint");
      cy.fixture('users.json').then(function (data) {
        TEST_USER_DATA = data.reader_user;
        cy.populateTestUser(TEST_USER_DATA);
      })
    }
    else {
        // do db reset if needed
        if (Cypress.env('do_reset_db') === true) {
          cy.logf("Resetting db state. Running db-reset.sh", Cypress.currentTest);
          cy.exec("./cypress/e2e/db-reset.sh");
          cy.wait(Cypress.env('wait_db_reset'));
        }
        else {
          cy.logf("Skipping resetting the db state.", Cypress.currentTest);
        }
      // seed the db with a user
      cy.visit("/")
      cy.logf("Running seed_reader_user.py", Cypress.currentTest)
      cy.exec("./cypress/e2e/db-seed-reader-user.sh")
    }

    // log in
    cy.logf("Logging in", Cypress.currentTest)
    cy.fixture('users.json').then(function (data) {
        users = data
        cy.loginViaApi(users.reader_user.email, users.reader_user.password)
    })

    cy.logf("End before() hook", Cypress.currentTest)
  })


  it("can view the Apps and models view", () => {

    cy.visit("/apps")

    cy.get('h3').should('contain', 'Applications')
  })

  it("can view the Projects view", () => {

    cy.visit("/projects/")

    cy.get('h3').should('have.text', 'Login required')
  })

  after(() => {

    if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
      cy.log("Cleaning up test data via Django endpoint");
      cy.cleanupTestUser(TEST_USER_DATA);
    }

    cy.logf("End after() hook", Cypress.currentTest)
})

})
