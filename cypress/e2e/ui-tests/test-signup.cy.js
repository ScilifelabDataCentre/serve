describe("Test sign up", () => {

    let users
    let TEST_USER_DATA

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest)

        cy.fixture('users.json').then(function (data) {
            users = data;
          })

        cy.logf("End before() hook", Cypress.currentTest)
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === false) {
            // reset and seed the database prior to every test
            if (Cypress.env('do_reset_db') === true) {
                cy.logf("Resetting db state. Running db-reset.sh", Cypress.currentTest);
                cy.exec("./cypress/e2e/db-reset.sh");
                cy.wait(Cypress.env('wait_db_reset'));
            }
            else {
                cy.logf("Skipping resetting the db state.", Cypress.currentTest);
            }
        }

        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })


    it("can create new user account with valid form input", () => {

        cy.visit("/signup/");
        cy.get("title").should("have.text", "Register | SciLifeLab Serve (beta)")

        cy.logf("Creating user account with valid input", Cypress.currentTest)
        cy.get('input[name=email]').type(users.signup_user.email);
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get('input[name="department"]').type('Biology Education Centre');

        cy.get("input#submit-id-save").click();

        cy.url().should("include", "accounts/login");
        cy.get('.alert-success').should(
            'contain',
            'Please check your email for a verification link.'
        );

        // TO-DO: add steps to check that email was sent, get token from email, go to email verification page, submit token there, then log in with new account
    })

    it("cannot create new user account with invalid form input", () => {

        // HTML form checks

        cy.visit("/signup/");
        cy.logf("First name is a required field in the HTML form", Cypress.currentTest)
        cy.get('input[name=first_name]').invoke('prop', 'validationMessage')
        cy.logf("Last name is a required field in the HTML form", Cypress.currentTest)
        cy.get('input[name=last_name]').invoke('prop', 'validationMessage')
        cy.logf("Department is not a required field in the HTML form", Cypress.currentTest)
        cy.get('input[name=department]').invoke('prop', 'validationMessage') // department is not a required field because those without uni  affiliation do not need to fill it out

        // Backend checks

        cy.logf("User without uni email asked for additional info by front and backend", Cypress.currentTest)
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

        cy.logf("Invalid email rejected by the backend", Cypress.currentTest)
        cy.visit("/signup/");
        cy.get('input[name=email]').type("test-email@test");
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_email"]').should('exist')

        cy.logf("Mismatching email and affiliation rejected by the backend", Cypress.currentTest)
        cy.visit("/signup/")
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=email]').clear().type("test-email@uu.se");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get('select[id=id_affiliation]').select('KTH Royal Institute of Technology')
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_affiliation"]').should('exist')

        cy.logf("Empty department rejected by the backend", Cypress.currentTest)
        cy.visit("/signup/")
        cy.get('input[name=email]').type("test-email@ki.se"); // department becomes a required field for uni emails
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type(users.signup_user.password);
        cy.get('input[name=password2]').type(users.signup_user.password);
        cy.get('input[name="department"]').clear();
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_department"]').should('exist')

        cy.logf("Mismatching passwords rejected by the backend", Cypress.currentTest)
        cy.visit("/signup/")
        cy.get('input[name=email]').type("test-email@test.kth.se");
        cy.get('input[name=first_name]').type("first name");
        cy.get('input[name=last_name]').type("last name");
        cy.get('input[name=password1]').type("first_password");
        cy.get('input[name=password2]').type("second_password");
        cy.get("input#submit-id-save").click();
        cy.get('[id="validation_password1"]').should('exist')
    })

    after(() => {
        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Cleaning up test data via Django endpoint");
            cy.fixture('users.json').then(function (data) {
            TEST_USER_DATA = data.signup_user;
            cy.cleanupTestUser(TEST_USER_DATA);
        });
        }
        cy.logf("End after() hook", Cypress.currentTest)
    })

})
