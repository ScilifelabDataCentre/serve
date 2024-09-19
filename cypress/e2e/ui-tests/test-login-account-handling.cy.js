describe("Test login, profile page view, password change, password reset", () => {

    let users

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest)

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
        cy.logf("Running seed-login-user.py", Cypress.currentTest)
        cy.exec("./cypress/e2e/db-seed-login-user.sh")

        cy.fixture('users.json').then(function (data) {
            users = data;
        })

        cy.logf("End before() hook", Cypress.currentTest)
    })


    it("can login an existing user through the UI when input is valid", () => {

        cy.visit("accounts/login/")
        cy.get("title").should("have.text", "Login | SciLifeLab Serve (beta)")

        cy.get('input[name=username]').type(users.login_user.email)
        cy.get('input[name=password]').type(users.login_user.password)

        cy.get("button").contains('Login').click()
            .then((href) => {
                cy.logf(href, Cypress.currentTest)
                cy.url().should("include", "projects")
                cy.get('h3').should('contain', 'My projects')
                cy.get('h3').parent().parent().find('p').first().should('not.contain', 'You need to be logged in')
            })
    })

    it("can login an existing user through the UI when input is valid using cypress command", () => {

        cy.loginViaUI(users.login_user.email, users.login_user.password)

    })

    it("can see user profile page", () => {
        cy.loginViaUI(users.login_user.email, users.login_user.password)
        cy.visit("/")
        cy.get('button.btn-profile').click()
        cy.get('li.btn-group').find('a').contains("My profile").click()
        cy.url().should("include", "user/profile/")

        cy.get('div.col-8').should("contain", users.login_user.email)
    })

    it("can change user password", () => {
        cy.loginViaUI(users.login_user.email, users.login_user.password)
        cy.visit("/")
        cy.get('button.btn-profile').click()
        cy.get('li.btn-group').find('a').contains("Change password").click()
        cy.url().should("include", "accounts/password_change/")

        cy.get('input[name=old_password]').type(users.login_user.password)
        cy.get('input[name=new_password1]').type(users.login_user.reset_password)
        cy.get('input[name=new_password2]').type(users.login_user.reset_password)
        cy.get('button.btn-primary').contains("Change").click()

        cy.url().should("include", "accounts/password_change/done/")
        cy.get('h1').should("contain", "Password changed")

        // check that the the old password does not work
        cy.clearCookies();
        cy.clearLocalStorage();
        Cypress.session.clearAllSavedSessions()
        cy.visit('/accounts/login/')
        cy.get('input[name=username]').type(users.login_user.email)
        cy.get('input[name=password]').type(users.login_user.password)
        cy.get('button.btn-primary').contains('Login').click()
        cy.get('div.alert-danger').should("contain", "Your email and password didn't match. Please try again.")

        // check that the new password works
        cy.visit('/accounts/login/')
        cy.get('input[name=username]').type(users.login_user.email)
        cy.get('input[name=password]').type(users.login_user.reset_password)
        cy.get('button.btn-primary').contains('Login').click()
        cy.visit('/projects/')
        cy.get('h3').should('contain', 'My projects')
    })

    it("can reset password with valid form input", () => {

        cy.visit("/accounts/password_reset/");
        cy.get("title").should("have.text", "Password reset | SciLifeLab Serve (beta)")
        cy.get("h2").should("contain", "Password reset")

        cy.get('input[type=email]').type(users.login_user.email);
        cy.get("input#submit-id-save").click();

        cy.url().should("include", "accounts/password_reset/done/");
        cy.get("p").should("contain", "We've emailed you instructions for setting your password.")

        // TO-DO: add steps to check that email was sent, click on the link, set new password, check that it is possible to log in with new password
    })

})
