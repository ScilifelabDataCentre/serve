describe("Test sign up", () => {

    let users

    beforeEach(() => {
        // reset and seed the database prior to every test
        if (Cypress.env('do_reset_db') === true) {
            cy.log("Resetting db state. Running db-reset.sh");
            cy.exec("./cypress/e2e/db-reset.sh");
            cy.wait(Cypress.env('wait_db_reset'));
        }
        else {
            cy.log("Skipping resetting the db state.");
        }
    })

    beforeEach(() => {
        cy.fixture('users.json').then(function (data) {
            users = data;
          })
    })

    it("can create new user account with valid form input", () => {

        cy.visit("/signup/");
        cy.get("title").should("have.text", "Register | SciLifeLab Serve")

        cy.get('input[name=email]').type(users.signup_user.email);
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get('input[name="department"]').type('Biology Education Centre');

        cy.get("input#submit-id-save").click();

        cy.url().should("include", "accounts/login");
        cy.get('.alert-success').should('contain', ' Please check your email to verify your account!');

        // TO-DO: add steps to check that email was sent, get token from email, go to email verification page, submit token there, then log in with new account
    })

})
