describe("Test brute force login attempts are blocked", () => {

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
        cy.log("Running seed-brute-force-login-user.py")
        cy.exec("./cypress/e2e/db-seed-brute-force-login-user.sh")
    })

    beforeEach(() => {
        cy.fixture('users.json').then(function (data) {
            users = data;
          })
    })

    it("can first login but repeated failed login attempts result in locked out account", () => {

        // First verify that the user can login
        cy.log("First verify that the user can login")
        cy.loginViaUI(users.brute_force_login_user.email, users.brute_force_login_user.password)
        cy.visit("/")
        cy.get('button.btn-profile').click()
        cy.get('li.btn-group').find('a').contains("My profile").click()
        cy.url().should("include", "user/profile/")
        cy.get('div.col-8').should("contain", users.brute_force_login_user.email)

        // Sign out before logging in again
        cy.log("Sign out before logging in again")
        cy.visit("accounts/logout/")
        cy.get("title").should("have.text", "Logout | SciLifeLab Serve (beta)")

        // Repeatedly perform failing login attempts
        let n_remaining_attempts = 4

        while (n_remaining_attempts > 0) {
            n_remaining_attempts--

            cy.log("Attempting an incorrect login attempt using loginViaUINoValidation")
            cy.loginViaUINoValidation(users.brute_force_login_user.email, "BAD-PASSWORD")
            // The user view should stay on login page
            cy.url().should("include", "accounts/login/")
            cy.get("p").contains("Your email and password didn't match").should("exist")
          }

        // Perform one more incorrect login attempt which should result in a locked account
        cy.log("Attempting an incorrect login attempt using loginViaUINoValidation")
        cy.loginViaUINoValidation(users.brute_force_login_user.email, "BAD-PASSWORD")
        // The user view should stay on login page
        cy.url().should("include", "accounts/login/")
        cy.get('h1').should("have.text", "Your account has been locked")

    })
})
