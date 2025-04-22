describe("Test brute force login attempts are blocked", () => {

    let users
    let TEST_USER_DATA


    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest)

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Populating test data via Django endpoint");
            cy.fixture('users.json').then(function (data) {
                TEST_USER_DATA = data.brute_force_login_user;
                cy.populateTestUser(TEST_USER_DATA);
            });
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
            cy.logf("Running seed-brute-force-login-user.py", Cypress.currentTest)
            cy.exec("./cypress/e2e/db-seed-brute-force-login-user.sh")
        }

        cy.logf("End before() hook", Cypress.currentTest)
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)

        cy.fixture('users.json').then(function (data) {
            users = data;
          })

        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("can first login but repeated failed login attempts result in locked out account", () => {

        // First verify that the user can login
        cy.logf("First verify that the user can login", Cypress.currentTest)
        cy.loginViaUI(users.brute_force_login_user.email, users.brute_force_login_user.password)
        cy.visit("/")
        cy.get('button.btn-profile').click()
        cy.get('li.btn-group').find('a').contains("My profile").click()
        cy.url().should("include", "user/profile/")
        cy.get('#id_email').should("contain.value", users.brute_force_login_user.email)

        // Sign out before logging in again
        cy.logf("Sign out before logging in again", Cypress.currentTest)
        cy.get('button.btn-profile').contains("Profile").click()
        cy.get('li.btn-group').find('button').contains("Sign out").click()
        cy.get("title").should("have.text", "Logout | SciLifeLab Serve (beta)")

        // Repeatedly perform failing login attempts
        let n_remaining_attempts = 4

        while (n_remaining_attempts > 0) {
            n_remaining_attempts--

            cy.logf("Attempting an incorrect login attempt using loginViaUINoValidation", Cypress.currentTest)
            cy.loginViaUINoValidation(users.brute_force_login_user.email, "BAD-PASSWORD")
            // The user view should stay on login page
            cy.url().should("include", "accounts/login/")
            cy.get("p").contains("Your email and password didn't match").should("exist")
          }

        // Perform one more incorrect login attempt which should result in a locked account
        cy.logf("Attempting an incorrect login attempt using loginViaUINoValidation", Cypress.currentTest)
        cy.loginViaUINoValidation(users.brute_force_login_user.email, "BAD-PASSWORD")
        // The user view should stay on login page
        cy.url().should("include", "accounts/login/")
        cy.get('h1').should("have.text", "Your account has been locked")

    })

    after(() => {
        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Cleaning up test data via Django endpoint");
            cy.cleanupTestUser(TEST_USER_DATA);
        }

        cy.logf("End after() hook", Cypress.currentTest)
    })
})
