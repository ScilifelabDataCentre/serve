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

    it("sees the Hardware and Environments settings tabs", () => {
        openProjectSettings(TEST_PROJECT_DATA.project_name);

        cy.get('.list-group').find('a').should('contain', 'Hardware');
        cy.get('.list-group').find('a').should('contain', 'Environments');
    });

    it("can create, view, and delete a flavor", () => {
        const flavor_name = "8 vCPU, 16 GB RAM";

        openProjectSettings(TEST_PROJECT_DATA.project_name);

        cy.get('.list-group').find('a').contains('Hardware').should('be.visible').click();

        // Create a new Hardware option
        cy.get('input[name="flavor_name"]').type(flavor_name);
        cy.get('input[name="cpu_lim"]').clear().type("8000m");
        cy.get('input[name="mem_lim"]').clear().type("16Gi");
        cy.get('input[name="ephmem_lim"]').clear().type("5000Mi");
        cy.get('input[name="gpu_req"]').clear().type("0");
        cy.get('button').contains("Create hardware").should('be.visible').click();

        cy.get('.list-group').find('a').contains('Hardware').should('be.visible').click();

        // Check that the Hardware option was added
        cy.contains('#flavors tbody tr', flavor_name).should('be.visible').within(() => {
                cy.contains('button', 'Details').click();
            });
        cy.get('#flavors .modal.show').should('be.visible').within(() => {
                cy.contains(`Details for ${flavor_name}`).should('be.visible');
                cy.contains(`Name: ${flavor_name}`).should('be.visible');
                cy.contains('CPU limit: 8000m').should('be.visible');
                cy.contains('Memory limit: 16Gi').should('be.visible');
                cy.contains('Ephemeral storage limit: 5000Mi').should('be.visible');
                cy.contains('GPU: 0').should('be.visible');
                cy.contains('button', 'Close').first().click();
            });

        // Delete the created Hardware option
        cy.contains('#flavors tbody tr', flavor_name).should('be.visible').within(() => {
                cy.contains('button', 'Delete').click();
            });
        cy.get('#flavors .modal.show').should('be.visible').within(() => {
                cy.contains(`Are you sure you want to delete`).should('be.visible');
                cy.contains('strong', flavor_name).should('be.visible');
                cy.contains('button', 'Delete').click();
            });

        // Confirm it was deleted
        cy.get('.list-group').find('a').contains('Hardware').should('be.visible').click();
        cy.contains('#flavors tbody tr', flavor_name).should('not.exist');
    });

    it("can create, view, and delete an environment", () => {
        const environment_name = "e2e privileged environment";
        const environment_repository = "docker.io";
        const environment_image = "jupyter/minimal-notebook:latest";
        const environment_app = "Jupyter Lab";

        openProjectSettings(TEST_PROJECT_DATA.project_name);

        cy.get('.list-group').find('a').contains('Environments').should('be.visible').click();

        // Create a new Environment
        cy.get('input[name="environment_name"]').type(environment_name);
        cy.get('input[name="environment_repository"]').clear().type(environment_repository);
        cy.get('input[name="environment_image"]').clear().type(environment_image);
        cy.get('#environment_app').select(environment_app);
        cy.get('button').contains("Create environment").should('be.visible').click();


        // Check that the environment exists and open Details
        cy.get('.list-group').find('a').contains('Environments').should('be.visible').click();
        cy.contains('#environments tbody tr', environment_name).should('be.visible').within(() => {
                cy.contains('button', 'Details').click();
            });

        // Check details of the created Environment
        cy.get('#environments .modal.show').should('be.visible').within(() => {
                cy.contains(`Details for ${environment_name}`).should('be.visible');
                cy.contains(`Name: ${environment_name}`).should('be.visible');
                cy.contains(`Repository: ${environment_repository}`).should('be.visible');
                cy.contains(`Image: ${environment_image}`).should('be.visible');
                cy.contains(`Applies to app type: ${environment_app}`).should('be.visible');
                cy.contains('button', 'Close').click();
            });

        // Delete the created Environment
        cy.contains('#environments tbody tr', environment_name).should('be.visible').within(() => {
                cy.contains('button', 'Delete').click();
            });
        cy.get('#environments .modal.show').should('be.visible').within(() => {
                cy.contains(`Delete environment ${environment_name}`).should('be.visible');
                cy.contains('Are you sure you want to delete').should('be.visible');
                cy.contains('strong', environment_name).should('be.visible');
                cy.contains('button', 'Delete').click();
            });

        cy.get('.list-group').find('a').contains('Environments').should('be.visible').click();
        cy.contains('#environments tbody tr', environment_name).should('not.exist');
    });

    it("can set a volume size directly and still request more", () => {
        openProjectSettings(TEST_PROJECT_DATA.project_name);
        cy.get('a[href="#storage"]').click();

        cy.logf("Both the privileged control and the request-more option are offered", Cypress.currentTest);
        cy.get('.resize-volume-input').first().should('be.visible');
        cy.get('.resize-volume-btn').first().should('be.visible');
        cy.contains('button', 'Request more').should('be.visible');
        cy.contains('Increase volume size').should('be.visible');
        cy.contains('up to 50 GB').should('be.visible');
        cy.contains('Need more than').should('be.visible');

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
        cy.get('.list-group').find('a').should('contain', 'Hardware');
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
        cy.get('.list-group').find('a').should('not.contain', 'Hardware');
    });

    after(() => {
        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.cleanupTestProject(PRIVILEGED_USER_DATA, TEST_PROJECT_DATA);
            cy.cleanupTestUser(PRIVILEGED_USER_DATA);
            cy.cleanupTestUser(COLLABORATOR_DATA);
        }
    });
});
