describe("Test storage settings functionality", () => {
    // Tests for storage settings in project settings page
    let TEST_USER_DATA;
    const TEST_PROJECT_DATA = {
        project_name: "e2e-storage-test-proj",
        project_description: "Project for testing storage settings",
    };

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest);

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Populating test data via Django endpoint");
            const TEST_APP_DATA = {
                app_slug: "custom-app",
                name: "storage-test-app",
                description: "App for testing storage paths",
                access: "public",
                port: 8000,
                mount_path: "/home/app/data",
                image: "ghcr.io/scilifelabdatacentre/example-streamlit:latest",
                source_code_url: "https://example.com"
            };

            cy.fixture('users.json').then(function (data) {
                TEST_USER_DATA = data.deploy_app_user;
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
        }

        cy.logf("End before() hook", Cypress.currentTest);
    });

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest);
        cy.fixture('users.json').then(function (data) {
            cy.loginViaApi(data.deploy_app_user.email, data.deploy_app_user.password);
        });
        cy.logf("End beforeEach() hook", Cypress.currentTest);
    });

    it("can navigate to storage settings", () => {
        cy.visit("/projects/");
        cy.contains('.card-title', TEST_PROJECT_DATA.project_name)
            .parents('.card-body')
            .siblings('.card-footer')
            .find('a:contains("Open")')
            .first()
            .click();
        
        // Go to settings
        cy.get('a[href*="settings"]').click();
        
        // Click storage tab
        cy.get('a[href="#storage"]').click();
        
        // Verify storage settings card is visible
        cy.get('.card-title').contains('Storage settings').should('be.visible');
    });

    it("can add and remove mount paths", () => {
        cy.visit(`/projects/${TEST_PROJECT_DATA.project_name}/settings?tab=storage`);
        
        // Add new path
        cy.get('.addPathBtn').first().click();
        cy.get('input[name^="paths_"]').last().type('/home/newpath');
        
        // Save changes
        cy.get('button[type="submit"]').contains('Save').click();
        
        // Verify success message
        cy.get('.alert-success').should('contain', 'Storage settings saved');
        
        // Remove the path
        cy.get('.removePathBtn').last().click();
        
        // Save changes
        cy.get('button[type="submit"]').contains('Save').click();
        
        // Verify success message
        cy.get('.alert-success').should('contain', 'Storage settings saved');
    });

    it("validates mount path format", () => {
        cy.visit(`/projects/${TEST_PROJECT_DATA.project_name}/settings?tab=storage`);
        
        // Try invalid path
        cy.get('.addPathBtn').first().click();
        cy.get('input[name^="paths_"]').last().type('/invalid/path');
        
        // Save changes
        cy.get('button[type="submit"]').contains('Save').click();
        
        // Verify error message
        cy.get('.alert').should('contain', 'Path /invalid/path must start with "/home" or "/srv"');
        
        // Fix path and try again
        cy.get('input[name^="paths_"]').last().clear().type('/home/valid/path');
        cy.get('button[type="submit"]').contains('Save').click();
        
        // Verify success
        cy.get('.alert-success').should('contain', 'Storage settings saved');
    });

    it("protects paths in use by apps", () => {
        cy.visit(`/projects/${TEST_PROJECT_DATA.project_name}/settings?tab=storage`);
        
        // Verify the app's mount path exists
        cy.get('input[value="/home/app/data"]').should('exist');
        
        // Verify it shows as in use
        cy.get('.input-group:contains("/home/app/data")')
            .find('.input-group-text')
            .should('contain', 'in use');
        
        // Verify no remove button for in-use path
        cy.get('.input-group:contains("/home/app/data")')
            .find('.removePathBtn')
            .should('not.exist');
    });

    it("shows which apps use each path", () => {
        cy.visit(`/projects/${TEST_PROJECT_DATA.project_name}/settings?tab=storage`);
        
        // Find the mount path used by our test app
        cy.get('.input-group:contains("/home/app/data")')
            .next('.form-text')
            .should('contain', 'Used by:')
            .and('contain', 'storage-test-app');
    });

    it("validates mount path during app creation", () => {
        cy.visit(`/projects/${TEST_PROJECT_DATA.project_name}`);
        
        // Click Create on Custom App
        cy.get('div.card-body:contains("Custom App")').siblings('.card-footer').find('a:contains("Create")').click();
        
        // Try invalid mount path
        cy.get('#id_mount_path').type('/invalid/path');
        cy.get('#submit-id-submit').click();
        cy.get('.invalid-feedback').should('contain', 'Path must start with "/home" or "/srv"');
        
        // Try valid mount path
        cy.get('#id_mount_path').clear().type('/home/app/data');
        cy.get('#submit-id-submit').should('not.be.disabled');
    });

    it("preserves default paths", () => {
        cy.visit(`/projects/${TEST_PROJECT_DATA.project_name}/settings?tab=storage`);
        
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
});
