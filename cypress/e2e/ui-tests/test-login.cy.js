describe("Test login", () => {

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
        cy.log("Running seed-login-user.py")
        cy.exec("./cypress/e2e/db-seed-login-user.sh")
    })

    beforeEach(() => {
        cy.fixture('users.json').then(function (data) {
            users = data;
          })
    })

    it("can login an existing user through the UI when input is valid", () => {

        cy.visit("accounts/login/")

        cy.get('input[name=username]').type(users.login_user.username)
        cy.get('input[name=password]').type(users.login_user.password)

        cy.get("button").contains('Login').click()
            .then((href) => {
                cy.log(href)
                cy.url().should("include", "projects")
                cy.get('h3').should('contain', 'My projects')
                cy.get('h3').parent().parent().find('p').first().should('not.contain', 'You need to be logged in')
            })
    })

    it("can login an existing user through the UI when input is valid using cypress command", () => {

        cy.loginViaUI(users.login_user.username, users.login_user.password)

    })

    it("Should have proper title", () => {
	cy.visit("accounts/login/")
        cy.get("title").should("have.text", "Login | SciLifeLab Serve")
    })
})
