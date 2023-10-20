describe("Test views as authenticated user", () => {

  // Tests performed as an authenticated user that only reads views
  // user: e2e_tests_login_tester

  let users

  before(() => {
            // do db reset if needed
            if (Cypress.env('do_reset_db') === true) {
              cy.log("Resetting db state. Running db-reset.sh");
              cy.exec("./cypress/e2e/db-reset.sh");
              cy.wait(Cypress.env('wait_db_reset'));
            }
          else {
              cy.log("Skipping resetting the db state.");
          }
          // seed the db with a user
          cy.visit("/")
          cy.log("Running seed_reader_user.py")
          cy.exec("./cypress/e2e/db-seed-reader-user.sh")
          // log in
          cy.log("Logging in")
          cy.fixture('users.json').then(function (data) {
              users = data

              cy.loginViaApi(users.reader_user.username, users.reader_user.password)
          })
  })

  beforeEach(() => {
  })


  it("can view the Apps view", () => {

    cy.visit("/apps")

    cy.get('h3').should('contain', 'apps')
  })

  it("can view the Models view", () => {

    cy.visit("/models/")

    cy.get('h3').should('contain', 'Models')
  })

  it("can view the Projects view", () => {

    cy.visit("/projects/")

    cy.get('h3').should('have.text', 'My projects')
  })

})
