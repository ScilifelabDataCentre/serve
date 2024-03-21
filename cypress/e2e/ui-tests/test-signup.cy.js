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
        cy.get("title").should("have.text", "Register | SciLifeLab Serve (beta)")

        cy.log("Creating user account with valid input")
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

    it("cannot create new user account with invalid form input", () => {

        // HTML form checks

        cy.visit("/signup/");
        cy.log("First name is a required field in the HTML form")
        cy.get('input[name=first_name]').invoke('prop', 'validationMessage').should('equal', 'Please fill out this field.')
        cy.log("Last name is a required field in the HTML form")
        cy.get('input[name=last_name]').invoke('prop', 'validationMessage').should('equal', 'Please fill out this field.')
        cy.log("Department is not a required field in the HTML form")
        cy.get('input[name=department]').invoke('prop', 'validationMessage').should('not.equal', 'Please fill out this field.') // department is not a required field because those without uni  affiliation do not need to fill it out

        // Backend checks

        cy.log("User without uni email asked for additional info by front and backend")
        cy.visit("/signup/");
        cy.get('[id="id_request_account_info"]').should('have.class', 'hidden')
        cy.get('input[name=email]').type("test-email@test.se"); // non-uni email
        cy.get('[id="id_request_account_info"]').should('not.have.class', 'hidden') // should be visible with a non-uni email
        cy.get('input[name=email]').clear().type("test-email@student.lu.se"); // student email
        cy.get('[id="id_request_account_info"]').should('not.have.class', 'hidden') // should be visible with a non-uni email
        // fill out the form
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_why_account_needed"]').should('exist')
        // reset and check that all works
        cy.get('input[name=email]').clear().type("test-email@uu.se");
        cy.get('[id="id_request_account_info"]').should('have.class', 'hidden')

        cy.log("Invalid email rejected by the backend")
        cy.visit("/signup/");
        cy.get('input[name=email]').type("test-email@test");
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_email"]').should('exist')

        cy.log("Mismatching email and affiliation rejected by the backend")
        cy.visit("/signup/")
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=email]').clear().type("test-email@uu.se");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get('select[id=id_affiliation]').select('KTH Royal Institute of Technology')
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_affiliation"]').should('exist')

        cy.log("Empty department rejected by the backend")
        cy.visit("/signup/")
        cy.get('input[name=email]').type("test-email@ki.se"); // department becomes a required field for uni emails
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get('input[name="department"]').clear();
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_department"]').should('exist')

        cy.log("Mismatching passwords rejected by the backend")
        cy.visit("/signup/")
        cy.get('input[name=email]').type("test-email@test.kth.se");
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type("first_password");
        cy.get('input[name=password2]').type("second_password");
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_password1"]').should('exist')
    })

})
