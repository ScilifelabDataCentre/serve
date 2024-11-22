describe("Test profile page edit", () => {

    //(uncaught exception) TypeError: request_account_field is null
    Cypress.on('uncaught:exception', (err, runnable) => {
        return false;
      });

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
        cy.logf("Running seed-profile-edit-user.py", Cypress.currentTest)
        cy.exec("./cypress/e2e/db-seed-profile-edit-user.sh")

        cy.fixture('users.json').then(function (data) {
            users = data;
        })

        cy.logf("End before() hook", Cypress.currentTest)
    })

    function editProfile(firstName, lastName, department) {

        cy.url().should("include", "edit-profile/")

        cy.get('#id_first_name').clear().type(firstName);
        cy.get('#id_last_name').clear().type(lastName);
        cy.get('#id_department').clear().type(department);
        cy.get('#submit-id-save').click();

        cy.contains(firstName).should('exist');
        cy.contains(lastName).should('exist');
        cy.contains(department).should('exist');
    }

    it("can change user profile information", () => {
        cy.loginViaUI(users.profile_edit_testuser.email, users.profile_edit_testuser.password)
        cy.visit("/")
        cy.get('button.btn-profile').click()
        cy.get('li.btn-group').find('a').contains("Edit profile").click()
        
        editProfile('changing fast name', 'changing last name', 'changing department name');

        cy.get('button.btn-profile').contains('a', 'Edit').click();

        // Checking it twice as edit option is in two different places.
        editProfile('changing fast name again', 'changing last name again', 'changing department name again');
    })
})
