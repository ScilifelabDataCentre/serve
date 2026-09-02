describe("Test privileged user functionality", () => {

    let PRIVILEGED_USER_DATA;
    let COLLABORATOR_DATA;

    const TEST_PROJECT_DATA = {
        project_name: "e2e-privileged-test-proj",
        project_description: "Project owned by a privileged user",
    };

    const openProjectSettings = (projectName) => {
        cy.visit("/projects/");
        cy.contains('.card-title', projectName)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .click();
        cy.get('[data-cy="settings"]').should('be.visible').click();
    };

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest);

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.fixture('users.json').then(function (data) {
                PRIVILEGED_USER_DATA = data.privileged_user;
                COLLABORATOR_DATA = data.privileged_collaborator;

                cy.populateTestPrivilegedUser(PRIVILEGED_USER_DATA);
                cy.populateTestProject(PRIVILEGED_USER_DATA, TEST_PROJECT_DATA);
                cy.populateTestPrivilegedUser(COLLABORATOR_DATA);
            });
        } else {
            if (Cypress.env('do_reset_db') === true) {
                cy.exec("./cypress/e2e/db-reset.sh");
                cy.wait(Cypress.env('wait_db_reset'));
            }
            cy.exec("./cypress/e2e/db-seed-privileged-user.sh");
        }

        cy.logf("End before() hook", Cypress.currentTest);
    });

    beforeEach(() => {
        cy.fixture('users.json').then(function (data) {
            cy.loginViaUI(data.privileged_user.email, data.privileged_user.password);
        });
    });

    it("sees the Flavors and Environments settings tabs", () => {
        openProjectSettings(TEST_PROJECT_DATA.project_name);

        cy.get('.list-group').find('a').should('contain', 'Flavors');
        cy.get('.list-group').find('a').should('contain', 'Environments');
    });

    it("can create and delete a flavor", () => {
        const flavor_name = "8 vCPU, 16 GB RAM";

        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('.list-group').find('a').should('be.visible').contains('Flavors').click();
        cy.get('input[name="flavor_name"]').type(flavor_name);
        cy.get('input[name="cpu_req"]').clear().type("100m");
        cy.get('input[name="cpu_lim"]').clear().type("8000m");
        cy.get('input[name="mem_req"]').clear().type("2Gi");
        cy.get('input[name="mem_lim"]').clear().type("16Gi");
        cy.get('button').should('be.visible').contains("Create flavor").click();

        cy.get('.list-group').find('a').should('be.visible').contains('Flavors').click();
        cy.get('#flavor_pk').should('contain', flavor_name);

        cy.get('#flavor_pk').select(flavor_name);
        cy.get('button').should('be.visible').contains("Delete flavor").click();

        cy.get('.list-group').find('a').should('be.visible').contains('Flavors').click();
        cy.get('#flavor_pk').should('not.contain', flavor_name);
    });

    it("can create an environment", () => {
        const environment_name = "e2e privileged environment";

        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('.list-group').find('a').should('be.visible').contains('Environments').click();
        cy.get('input[name="environment_name"]').type(environment_name);
        cy.get('input[name="environment_repository"]').clear().type("docker.io");
        cy.get('input[name="environment_image"]').clear().type("jupyter/minimal-notebook:latest");
        cy.get('#environment_app').select('Jupyter Lab');
        cy.get('button').should('be.visible').contains("Create environment").click();

        cy.get('.list-group').find('a').should('be.visible').contains('Environments').click();
        cy.get('#environment_pk').should('contain', environment_name);
    });

    it("sets a volume size directly instead of requesting more storage", () => {
        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('a[href="#storage"]').click();

        cy.get('.resize-volume-input').first().should('be.visible');
        cy.get('.resize-volume-btn').first().should('be.visible');
        cy.contains('button', 'Request more').should('not.exist');

        cy.logf("A size below the current one is refused with a message, not an alert", Cypress.currentTest);
        cy.get('.resize-volume-input').first().clear().type("1");
        cy.get('.resize-volume-btn').first().click();
        cy.contains('never shrunk').should('be.visible');
    });

    it("grants and revokes privileged access for a project member", () => {
        cy.logf("Give the collaborator plain access first", Cypress.currentTest);
        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('a[href="#access"]').click();
        cy.get('input[name=selected_user]').clear().type(COLLABORATOR_DATA.email);
        cy.get('button').contains('Grant access').click();

        cy.logf("The member has no privileged access yet", Cypress.currentTest);
        cy.get('a[href="#access"]').click();
        cy.contains('tr', COLLABORATOR_DATA.email)
            .find('.privileged-access-toggle')
            .should('not.be.checked');

        cy.logf("Granting it via the toggle", Cypress.currentTest);
        cy.contains('tr', COLLABORATOR_DATA.email).find('.privileged-access-toggle').check();
        cy.get('a[href="#access"]').click();
        cy.contains('tr', COLLABORATOR_DATA.email)
            .find('.privileged-access-toggle')
            .should('be.checked');

        cy.logf("The member can now manage resources in this project", Cypress.currentTest);
        Cypress.session.clearAllSavedSessions();
        cy.loginViaUI(COLLABORATOR_DATA.email, COLLABORATOR_DATA.password);
        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('.list-group').find('a').should('contain', 'Flavors');
        cy.logf("...but cannot pass it on", Cypress.currentTest);
        cy.get('a[href="#access"]').click();
        cy.get('.privileged-access-toggle').should('not.exist');

        cy.logf("The owner can take it away again", Cypress.currentTest);
        Cypress.session.clearAllSavedSessions();
        cy.loginViaUI(PRIVILEGED_USER_DATA.email, PRIVILEGED_USER_DATA.password);
        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('a[href="#access"]').click();
        cy.contains('tr', COLLABORATOR_DATA.email).find('.privileged-access-toggle').uncheck();

        Cypress.session.clearAllSavedSessions();
        cy.loginViaUI(COLLABORATOR_DATA.email, COLLABORATOR_DATA.password);
        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('.list-group').find('a').should('not.contain', 'Flavors');
    });

    after(() => {
        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.cleanupTestProject(PRIVILEGED_USER_DATA, TEST_PROJECT_DATA);
            cy.cleanupTestUser(PRIVILEGED_USER_DATA);
            cy.cleanupTestUser(COLLABORATOR_DATA);
        }
    });
});
