describe("Test storage settings functionality", () => {
    // Tests for storage settings in project settings page
    const testRunId = `${Date.now()}-${Cypress._.random(1000, 9999)}`;
    let users
    let TEST_USER_DATA;
    const getEndpointUserData = (userData) => ({
        ...userData,
        // Use a spec-specific account to avoid clashes with other specs in parallel CI runs.
        email: `no-reply-storage-settings-${testRunId}@scilifelab.uu.se`,
        username: `no-reply-storage-settings-${testRunId}@scilifelab.uu.se`
    });
    const TEST_PROJECT_DATA = {
        project_name: `e2e-storage-test-proj-${testRunId}`,
        project_description: "Project for testing storage settings",
    };

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest);

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Populating test data via Django endpoint");
            const TEST_APP_DATA = {
                app_slug: "customapp",
                name: "storage-test-app",
                description: "App for testing storage paths",
                access: "public",
                port: 8000,
                image: "ghcr.io/scilifelabdatacentre/example-streamlit:latest",
                source_code_url: "https://example.com",
                mount_path: "default"  // Use the default /home/data mount path
            };

            cy.fixture('users.json').then(function (data) {
                TEST_USER_DATA = getEndpointUserData(data.deploy_app_user);
                users = { ...data, deploy_app_user: TEST_USER_DATA };
                cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                cy.cleanupTestUser(TEST_USER_DATA);
                cy.populateTestUser(TEST_USER_DATA);
                cy.populateTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                cy.populateTestApp(TEST_USER_DATA, TEST_PROJECT_DATA, TEST_APP_DATA);
            });
        } else {
            if (Cypress.env('do_reset_db') === true) {
                cy.logf("Resetting db state. Running db-reset.sh", Cypress.currentTest);
                cy.exec("./cypress/e2e/db-reset.sh");
                cy.wait(Cypress.env('wait_db_reset'));
            }
            cy.exec("./cypress/e2e/db-seed-deploy-app-user.sh");

            // Note: For alternative data population methods, the shell script approach
            // would need to be extended to create both project and app data.
            // Currently db-seed-deploy-app-user.sh only creates a user.
        }

        cy.logf("End before() hook", Cypress.currentTest);
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest);
        cy.fixture('users.json').then(function (data) {
            users = data;
            if (Cypress.env('manage_test_data_via_django_endpoint_views') === true && TEST_USER_DATA) {
                users.deploy_app_user = TEST_USER_DATA;
            }
            cy.loginViaUI(users.deploy_app_user.email, users.deploy_app_user.password);
        })
        cy.logf("End beforeEach() hook", Cypress.currentTest);
    })

    it("can navigate to storage settings", () => {
        cy.visit("/projects/")
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Go to settings
        cy.get('[data-cy="settings"]').should('be.visible').click();

        // Click storage tab
        cy.get('a[href="#storage"]').click();

        // Verify storage settings card is visible
        cy.get('.card-title').contains('Storage settings').should('be.visible');
    });

    it("can add and remove mount paths", () => {
        // Navigate to project via UI to get correct slug
        cy.visit("/projects/");
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Go to settings
        cy.get('[data-cy="settings"]').should('be.visible').click();

        // Click storage tab
        cy.get('a[href="#storage"]').click();

        // Add new path
        cy.get('.addPathBtn').first().click();
        cy.get('input[name^="paths_"]:visible').last().type('/home/newpath');

        // Save changes (target storage form specifically)
        cy.get('#storage form button[type="submit"]').contains('Save').click();

        // Verify success message
        cy.get('.alert-success').should('contain', 'Storage settings saved');

        // Remove the path
        cy.get('.removePathBtn:visible').last().scrollIntoView().click({ force: true });

        // Save changes (target storage form specifically)
        cy.get('#storage form button[type="submit"]').contains('Save').click();

        // Verify success message
        cy.get('.alert-success').should('contain', 'Storage settings saved');
    });

    it("validates mount path format", () => {
        // Navigate to project via UI to get correct slug
        cy.visit("/projects/");
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Go to settings
        cy.get('[data-cy="settings"]').should('be.visible').click();

        // Click storage tab
        cy.get('a[href="#storage"]').click();

        // Try invalid path
        cy.get('.addPathBtn').first().click();
        cy.get('input[name^="paths_"]:visible').last().type('/invalid/path');

        // Save changes (target storage form specifically)
        cy.get('#storage form button[type="submit"]').contains('Save').click();

        // Verify error message
        cy.get('.alert').should('contain', 'Path /invalid/path must start with "/home" or "/srv"');

        // Fix path and try again
        cy.get('input[name^="paths_"]:visible').last().clear().type('/home/valid/path');
        cy.get('#storage form button[type="submit"]').contains('Save').click();

        // Verify success
        cy.get('.alert-success').should('contain', 'Storage settings saved');
    });

    it("protects paths in use by apps", () => {
        // Navigate to project via UI to get correct slug
        cy.visit("/projects/");
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Go to settings
        cy.get('[data-cy="settings"]').should('be.visible').click();

        // Click storage tab
        cy.get('a[href="#storage"]').click();

        // Verify the app's mount path exists
        cy.get('input[value="/home/data"]').should('exist');

        // Verify it shows as in use (displays usage information)
        cy.get('input[value="/home/data"]')
            .parents('.input-group')
            .next('.form-text')
            .should('contain', 'Used by:');

        // Verify no remove button for in-use path
        cy.get('input[value="/home/data"]')
            .parents('.input-group')
            .find('.removePathBtn')
            .should('not.exist');
    });

    it("shows which apps use each path", () => {
        // Navigate to project via UI to get correct slug
        cy.visit("/projects/");
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Go to settings
        cy.get('[data-cy="settings"]').should('be.visible').click();

        // Click storage tab
        cy.get('a[href="#storage"]').click();

        // Find the mount path used by our test app
        cy.get('input[value="/home/data"]')
            .parents('.input-group')
            .next('.form-text')
            .should('contain', 'Used by:')
            .and('contain', 'storage-test-app');
    });

    it("validates mount path during app creation", () => {
        // Navigate to project via UI to get correct slug
        cy.visit("/projects/");
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Click Create on Custom App
        cy.get('div.card-body:contains("Custom App")')
            .siblings('.card-footer')
            .find('a:contains("Create")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Verify mount path dropdown is available with default option
        cy.get('#id_mount_path').should('exist');
        cy.get('#id_mount_path option:contains("/home/data")').should('exist');

        // Select a valid mount path
        cy.get('#id_mount_path').select('/home/data (project-vol (' + TEST_PROJECT_DATA.project_name + '))');
        cy.get('#submit-id-submit').should('not.be.disabled');
    });

    it("preserves default paths", () => {
        // Navigate to project via UI to get correct slug
        cy.visit("/projects/");
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .scrollIntoView()
            .click({ force: true });

        // Go to settings
        cy.get('[data-cy="settings"]').should('be.visible').click();

        // Click storage tab
        cy.get('a[href="#storage"]').click();

        // Verify default paths are readonly
        cy.get('.input-group[data-default="1"] input').should('have.attr', 'readonly');

        // Verify default paths show default badge
        cy.get('.input-group[data-default="1"]')
            .find('.input-group-text')
            .should('contain', 'default');

        // Verify no remove button for default paths
        cy.get('.input-group[data-default="1"]')
            .find('.removePathBtn')
            .should('not.exist');
    });

    after(() => {
        cy.logf("Begin after() hook", Cypress.currentTest);

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Cleaning up test data via Django endpoint");
            cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
            cy.cleanupTestUser(TEST_USER_DATA);
        }
        // Note: For alternative data population methods, cleanup would need to be
        // implemented according to how the data was created

        cy.logf("End after() hook", Cypress.currentTest);
    });
});
