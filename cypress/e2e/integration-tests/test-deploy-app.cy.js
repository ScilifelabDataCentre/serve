describe("Test deploying app", () => {

    // TODO: This entire test class needs to be reworked.
    // There are good test ideas here but there needs to be made some fixes
    // and improvements similar to in ui-tests/test-user-manage-apps.cy.js
    // Note that this test class however can and should also test the k8s
    // integration much more.

    // Tests performed as an authenticated user that creates and deletes apps.
    // Note that these tests may depend on k8s deployments and may be long-running tests.
    // Warning: some of these tests may intermittenly fail depending on the available resources.

    // The default command timeout should not be so long
    // Instead use longer timeouts on specific commands where deemed necessary and valid
    const defaultCmdTimeoutMs = 10000
    // The longer timeout is often used when waiting for k8s operations to complete
    const longCmdTimeoutMs = 240000

    // Function to verify the displayed app status
    // Function to verify the displayed app permission level
    // Function to verify the expected_latest_user_action from data-app-action
    // Function to verify the expected_k8s_app_status from data-k8s-app-status

   const verifyAppStatus = (
    app_name,
    expected_status,
    expected_latest_user_action,
    expected_data_k8s_app_status,
    expected_permission
) => {
    // Find the application row with timeout
    cy.contains('a', app_name, { timeout: longCmdTimeoutMs })
        .closest('tr')
        .within(() => {

            // Verify application status with explicit timeout
            if (expected_status != "") {
                cy.get('[data-cy="appstatus"]', { timeout: longCmdTimeoutMs })
                    .should('have.attr', 'title', expected_status);
            }

            // Verify latest user action if specified with explicit timeout
            if (expected_latest_user_action != "") {
                cy.get('[data-cy="appstatus"]', { timeout: longCmdTimeoutMs })
                    .should('have.attr', 'data-app-action', expected_latest_user_action);
            }

            // Verify data-k8s-app-status if specified with explicit timeout
            if (expected_data_k8s_app_status != "") {
                cy.get('[data-cy="appstatus"]', { timeout: longCmdTimeoutMs })
                    .should('have.attr', 'data-k8s-app-status', expected_data_k8s_app_status);
            }

            // Verify permission level if specified with explicit timeout
            if (expected_permission != "") {
                cy.get('[data-cy="app-permission"]', { timeout: longCmdTimeoutMs })
                    .should('contain', expected_permission);
            }
        });
};
    // if any previous test is failed then that app will remain.
    // this may fail the next test too.
    // So, before starting a next test, we are ensuring
    // one more time that the previous app is deleted.
    const deleteAppIfExists = (app_name, project_name) => {

        cy.visit("/projects/");

        cy.contains('.card-title', project_name)
                .parents('.card-body')
                .siblings('.card-footer')
                .find('a:contains("Open")')
                .first()
                .click();

        // Check if app exists
        cy.get('body').then(($body) => {
        if ($body.find(`tr:contains("${app_name}")`).length) {
            cy.log(`Deleting existing app: ${app_name}`);

            // Delete workflow
            cy.get(`tr:contains("${app_name}")`)
                .find('i.bi-three-dots-vertical')
                .click();

            cy.get(`tr:contains("${app_name}")`)
                .find('a.confirm-delete')
                .click();

            cy.get('button').contains('Delete').click();

            // Verify deletion
            cy.contains(`tr:contains("${app_name}")`).should('not.exist');
            cy.log(`Successfully deleted app: ${app_name}`);
        }
        else {
            cy.log(`No app named "${app_name}" found - skipping deletion`);
        }
        });
    };



    // user: e2e_tests_deploy_app_user
    let users
    let TEST_USER_DATA
    const TEST_PROJECT_DATA = {
        project_name: "e2e-deploy-app-test",
        project_description: "e2e-deploy-app-test-desc",
    };


    before({ defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
        cy.logf("Begin before() hook", Cypress.currentTest)

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
                cy.log("Populating test data via Django endpoint");
                cy.fixture('users.json').then(function (data) {
                    TEST_USER_DATA = data.deploy_app_user;
                    cy.populateTestUser(TEST_USER_DATA);
                    cy.populateTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                })
            }

        else {

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
            cy.logf("Running seed-deploy-app-user.py", Cypress.currentTest)
            cy.exec("./cypress/e2e/db-seed-deploy-app-user.sh")
            // username in fixture must match username in db-reset.sh
            cy.fixture('users.json').then(function (data) {
                users = data

                cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password)
            })
            const project_name = "e2e-deploy-app-test"
            cy.createBlankProject(project_name)
        }


        cy.logf("End before() hook", Cypress.currentTest)
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)

        // username in fixture must match username in db-reset.sh
        cy.logf("Logging in", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password)
        })

        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("can deploy a project and public app using the custom app chart", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name_project = "e2e-custom-example-project"
        const app_name_public = "e2e-custom-example-public"
        const app_name_public_2 = "e2e-custom-example-2-public"
        const app_description = "e2e-custom-description"
        const app_description_2 = "e2e-custom-2-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const image_name_2 = "ghcr.io/scilifelabdatacentre/example-streamlit:230921-1443"
        const image_port = "8501"
        const image_port_2 = "8502"
        const app_path = "/home/username"
        const app_path_2 = "/home/username/app"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"
        const app_source_code_public = "https://doi.org/example"
        const default_url_subpath = "default/url/subpath/"
        const changed_default_url_subpath = "changed/subpath/"
        const invalid_default_url_subpath = "€% / ()"

        let volume_display_text = "project-vol (" + project_name + ")"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with project permissions
            cy.logf("Now creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_project)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            cy.get('#id_volume').select(volume_display_text)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_path').clear().type(app_path)
            cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').clear().type(default_url_subpath) // provide default_url_subpath
            cy.get('#submit-id-submit').contains('Submit').click()
            // check that the app was created
            verifyAppStatus(app_name_project, "Running", "Creating", "Running", "project")
            // check that the default URL subpath was created
            cy.contains('a', app_name_project)
                  .should('have.attr', 'href')
                  .and('include', default_url_subpath);
            // check that the app is not visible under public apps
            cy.visit('/apps/')
            // Verify heading with correct text and encoding
            cy.get('h3').should('contain', 'Public Applications & Models');
            cy.contains('h5.card-title', app_name_project).should('not.exist')

            // Verify empty state when no apps exist
            // cy.get('.tag-list').should('be.empty');
            cy.contains('h5.card-title', app_name_project).should('not.exist');

            // make this app public as an update and check that it works
            cy.logf("Now making the project app public", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_project + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_project + '")').find('a').contains('Settings').click()
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.get('#submit-id-submit').contains('Submit').click()
            verifyAppStatus(app_name_project, "Running", "Changing", "Running", "public")

            // Wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
                verifyAppStatus(app_name_project,  "Running", "Changing", "Running", "public")
            })

            cy.logf("Now deleting the project app (by now public)", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_project + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_project + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()

            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_project + '")').should('not.exist')
            })

            // Create a public app and verify that it is displayed on the public apps page
            cy.logf("Now creating a public app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()

            cy.get('#id_name').type(app_name_public)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_path').clear().type(app_path)
            cy.get('#id_volume').select(volume_display_text)
            cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').clear().type(default_url_subpath) // provide default_url_subpath
            cy.get('#submit-id-submit').contains('Submit').click()

            verifyAppStatus(app_name_public,  "Running", "Creating", "Running", "public")

            // Wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name_public,  "Running", "Creating", "Running", "public")
            })

            // check that the default URL subpath was created
            cy.contains('a', app_name_public)
                  .should('have.attr', 'href')
                  .and('include', default_url_subpath);

            cy.visit("/apps")
            cy.get('h5.card-title').should('contain', app_name_public)
            cy.get('.card-text').find('p').should('contain', app_description)

            // Check that the public app is displayed on the homepage
            cy.logf("Now checking if the public app is displayed when not logged in.", Cypress.currentTest)
            cy.visit("/home/")
            cy.get('h5').should('contain', app_name_public)
            // Log out and check that the public app is still displayed on the homepage
            cy.clearCookies();
            cy.clearLocalStorage();
            Cypress.session.clearAllSavedSessions()
            cy.visit('/projects/')
            cy.get('h3').should('contain', 'Login required') // check that logout worked
            cy.visit("/")
            cy.get('h5').should('contain', app_name_public)
            // Log back in
            cy.fixture('users.json').then(function (data) {
                users = data
                cy.loginViaUI(users.deploy_app_user.email, users.deploy_app_user.password)
            })

            // Check that the logs page opens for the app
            cy.logf("Now checking that the logs page for the app opens", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public + '")').find('a').contains('Logs').click()
            cy.get('h3').should('contain', "Logs")

            // Try changing the name, description, etc. of the app and verify it works
            cy.logf("Now changing the name and description of the public app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_public) // name should be same as before
            cy.get('#id_name').clear().type(app_name_public_2) // now change name
            cy.get('#id_description').should('have.value', app_description) // description should be same as set before
            cy.get('#id_description').clear().type(app_description_2) // now change description
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            // checking that a) permissions can be changed to 'Link'; b) that the corresponding text field is shown and mandatory
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').should('be.visible')
            cy.get('#id_note_on_linkonly_privacy').clear().type(link_privacy_type_note)
            cy.get('#id_volume').find(':selected').should('contain', 'project-vol')
            cy.get('#id_port').should('have.value', image_port)
            cy.get('#id_port').clear().type(image_port_2)
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_image').clear().type(image_name_2)
            cy.get('#id_path').should('have.value', app_path)
            cy.get('#id_path').clear().type(app_path_2)
            cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').should('have.value', default_url_subpath) // default_url_subpath should be same as before
            cy.get('#id_default_url_subpath').clear().type(changed_default_url_subpath) // provide changed_default_url_subpath
            cy.get('#submit-id-submit').contains('Submit').click()

            // NB: it will get status "Running" but it won't work because the new port is incorrect
            verifyAppStatus(app_name_public_2,  "Running", "Changing", "Running", "link")

            // Wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name_public_2,  "Running", "Changing", "Running", "link")
            })

            // check that the default URL subpath was changed
            cy.contains('a', app_name_public_2)
                  .should('have.attr', 'href')
                  .and('include', changed_default_url_subpath);

            // Check that the changes were saved
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_public_2)
            cy.get('#id_description').should('have.value', app_description_2)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_note_on_linkonly_privacy').should('have.value', link_privacy_type_note)
            cy.get('#id_port').should('have.value', image_port_2)
            cy.get('#id_image').should('have.value', image_name_2)
            cy.get('#id_path').should('have.value', app_path_2)
            cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').should('have.value', changed_default_url_subpath) // changed_url_subpath should be same as before

            // Make sure that giving invalid input in default_url_subpath field results in an error
            cy.get('#id_default_url_subpath').clear().type(invalid_default_url_subpath) // provide invalid_default_url_subpath
            cy.get('#submit-id-submit').contains('Submit').click() // this should trigger the error

            // check this invalid_default_url_subpath error was matched
            cy.get('.client-validation-feedback.client-validation-invalid')
      .should('exist')
      .and('include.text', 'Your custom URL subpath is not valid, please correct it');

            // Delete the created public app and verify that it is deleted from public apps page
            cy.logf("Now deleting the public app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()

            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_public_2 + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            // Verify heading with correct text and encoding
            cy.get('h3').should('contain', 'Public Applications & Models');
            cy.contains('h5.card-title', app_name_public_2).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    // This test may only work against a Serve instance running on our cluster. as
    // it takes a huge amount of time. It does not work on GitHub CI. So it's better
    // to skip it now. As we have Django endpoints, so it can be locally tested directly
    // in the Serve-dev instance.
    // We need to add a test here for validating Site-dir option. See SS-1206 for details
    it("can deploy a shiny app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-custom-example-project", "e2e-deploy-app-test")
        deleteAppIfExists("e2e-custom-example-2-public", "e2e-deploy-app-test")


        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-shiny-example"
        const app_description = "e2e-shiny-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/shiny-adhd-medication-sweden:20240117-062031"
        const image_port = "3838"
        const createResources = Cypress.env('create_resources');
        const app_type = "Shiny App"

        if (createResources === true) {
            cy.logf("Creating a shiny app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()

            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'public')

            cy.logf("Checking that all shiny app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            cy.logf("Checking that the shiny app is displayed on the public apps page", Cypress.currentTest)
            cy.visit("/apps")
            cy.get('h5.card-title').should('contain', app_name)
            cy.get('.card-text').find('p').should('contain', app_description)

            cy.logf("Checking that instructions for running the app locally are displayed on public apps page", Cypress.currentTest)
            cy.contains('.card', app_name).within(() => {
                cy.get('a[data-bs-target="#dockerInfoModal"]').click()
            })
            cy.get('div#dockerInfoModal').should('be.visible')
            cy.get('code').first().should('contain', image_name)
            cy.get('code').first().should('contain', image_port)
            cy.get('div.modal-footer').find('button').contains('Close').click()

            cy.logf("Checking that source code URL is displayed on the public apps page", Cypress.currentTest)
            cy.visit("/apps")
            cy.contains('.card', app_name).within(() => {
                cy.get('a#source-code-url').should('have.attr', 'href', source_code_url)
            })
            cy.visit("/projects/")
            cy.logf("Deleting the shiny app", Cypress.currentTest)
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can deploy a dash app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-shiny-example", "e2e-deploy-app-test")

        // Simple test to create and delete a Dash app
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-dash-example"
        const app_description = "e2e-dash-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources');
        const app_type = "Dash App"

        if (createResources === true) {
            // Create Dash app
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            // Verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Delete the Dash app
            cy.logf("Deleting the dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can deploy a tissuumaps app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-dash-example", "e2e-deploy-app-test")

        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-tissuumaps-example"
        const app_description = "e2e-tissuumaps-description"
        const createResources = Cypress.env('create_resources');
        const app_type = "TissUUmaps App"

        let volume_display_text = "project-vol (" + project_name + ")"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            cy.logf("Creating a tisuumaps app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()

            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_volume').select(volume_display_text)
            cy.get('#submit-id-submit').contains('Submit').click()

            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            // Wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name, "Running", "Creating", "Running", "public")
            })

            cy.logf("Checking that all tissuumaps app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_volume').find(':selected').should('contain', 'project-vol')

            cy.logf("Deleting the tissuumaps app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can deploy a gradio app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-tissuumaps-example", "e2e-deploy-app-test")

        // Simple test to create and delete a Gradio app
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-gradio-example"
        const app_description = "e2e-gradio-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/gradio-flower-classification:20241118-174426"
        const image_port = "7860"
        const createResources = Cypress.env('create_resources');
        const app_type = "Gradio App"

        if (createResources === true) {
            // Create Gradio app
            cy.logf("Creating a gradio app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            // Verify Gradio app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Delete the Gradio app
            cy.logf("Deleting the gradio app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can deploy a streamlit app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-gradio-example", "e2e-deploy-app-test")

        // Simple test to create and delete a Streamlit app
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-streamlit-example"
        const app_description = "e2e-streamlit-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/streamlit-image-to-smiles:20241112-183549"
        const image_port = "8501"
        const createResources = Cypress.env('create_resources');
        const app_type = "Streamlit App"

        if (createResources === true) {
            // Create Streamlit app
            cy.logf("Creating a streamlit app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            // Verify Streamlit app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Delete the Streamlit app
            cy.logf("Deleting the dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can modify app settings resulting in NO k8s redeployment shows correct app status", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-streamlit-example", "e2e-deploy-app-test")

        // An advanced test to verify user can modify app settings such as the name and description
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-change-app-settings-no-redeploy"
        const app_name_edited = app_name + "-edited"
        const app_description = "e2e-change-app-settings-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources');
        const app_type = "Dash App"

        if (createResources === true) {
            // Create Dash app
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            // Verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Edit Dash app: modify the app name and description
            cy.logf("Editing the dash app settings (non redeployment fields)", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            // Here we change the app name from app_name to app_name_edited
            cy.get('#id_name').type("-edited")
            cy.get('#id_description').type(", edited description.")
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // Verify that the app status still equals Running
            verifyAppStatus(app_name_edited,"Running", "Changing", "Running", "public")

            // Wait for 20 seconds and check the app status again
            // This is a brittle part of the test, therefore we wait a longer time to see if the status (incorrectly) changes
            cy.wait(20000).then(() => {
              verifyAppStatus(app_name_edited, "Running", "Changing", "Running", "public")
            })

            // Delete the Dash app
            cy.logf("Deleting the dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_edited + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_edited + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_edited + '")').should('not.exist')
            })

            // The app name is not visible anymore, so not possible to catch it in verifyAppStatus()
            // verifyAppStatus(app_name_edited, "Deleted", "")

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name_edited).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can modify app settings resulting in k8s redeployment shows correct app status", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-change-app-settings-no-redeploy-edited", "e2e-deploy-app-test")

        // An advanced test to verify user can modify app settings resulting in k8s redeployment (image)
        // still shows the correct app status.
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-change-app-settings-redeploy"
        const app_description = "e2e-change-app-settings-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources');
        const app_type = "Dash App"

        if (createResources === true) {
            // Create Dash app
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            // Verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Edit Dash app: modify the app image to an invalid or empty image
            cy.logf("Editing the dash app settings field Image to an invalid value", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_image').clear()
            cy.get('#submit-id-submit').contains('Submit').click()
            // Stay on the Settings page
            cy.url().should("include", "/apps/settings")

            // Edit Dash app: modify the app image back to a valid image
            cy.logf("Editing the dash app settings field Image to a valid value", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_image').clear().type(image_name)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // Verify that the app status now equals Running
            verifyAppStatus(app_name, "Running", "Changing", "Running", "public")

            // Wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name, "Running", "Changing", "Running", "public")
            })

            // Delete the Dash app
            cy.logf("Deleting the dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can set and change subdomain", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-change-app-settings-redeploy", "e2e-deploy-app-test")

        // A test to verify creating an app and changing the subdomain
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-subdomain-change"
        const app_description = "e2e-subdomain-change-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources');
        const app_type = "Dash App"
        const subdomain_change = "subdomain-change"

        if (createResources === true) {
            // Create Dash app without custom subdomain
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "public")

            // Verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Edit Dash app: change the suibdomain to a custom value
            cy.logf("Editing the dash app settings field subdomain", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_subdomain').clear().type(subdomain_change)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);
            // Verify that the app status now equals Running
            verifyAppStatus(app_name, "Running", "Changing", "Running", "public")

            // Wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
                verifyAppStatus(app_name, "Running", "Changing", "Running", "public")
              })

            // Delete the Dash app
            cy.logf("Deleting the dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public Applications & Models')
            cy.contains('h5.card-title', app_name).should('not.exist')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }

    })

    it("can set and change custom subdomain several times", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-subdomain-change", "e2e-deploy-app-test")

        // An advanced test to verify creating apps and changing subdomains. Steps taken:
        // 1. Create app e2e-subdomain-example, subdomain=subdomain-test
        // 2. Attempt create app e2e-second-subdomain-example, using subdomain=subdomain-test
        // 3. Create app e2e-second-subdomain-example, subdomain=subdomain-test2
        // 4. Change the subdomain of the first app to subdomain=subdomain-test3
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-subdomain-example"
        const app_name_2 = "e2e-second-subdomain-example"
        const app_description = "e2e-subdomain-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"
        const subdomain = "subdomain-test"
        const subdomain_2 = "subdomain-test2"
        const subdomain_3 = "subdomain-test3"

        let volume_display_text = "project-vol (" + project_name + ")"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            // Create an app and set a custom subdomain for it
            cy.logf("Now creating an app with a custom subdomain", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            // fill out other fields
            cy.get('#id_name').clear().type(app_name)
            cy.get('#id_description').clear().type(app_description)
            cy.get('#id_port').clear().type("8501")
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_volume').select(volume_display_text)
            cy.get('#id_path').clear().type("/home")
            // fill out subdomain field
            cy.get('#id_subdomain').clear().type(subdomain)

            // create the app
            cy.get('#submit-id-submit').contains('Submit').click()

            verifyAppStatus(app_name, "Running", "Creating", "Running", "project")

            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain)

            // Try using the same subdomain the second time
            cy.logf("Now trying to create an app with an already taken subdomain", Cypress.currentTest)
            // cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()

            cy.get('#id_name').clear().type(app_name_2)
            cy.get('#id_port').clear().type("8501")
            cy.get('#id_image').clear().type(image_name)

            // fill out subdomain field
            cy.get('#id_subdomain').clear().type(subdomain)
            cy.get('#id_subdomain').blur();

            cy.get('#div_id_subdomain', {timeout: longCmdTimeoutMs}).should('contain.text', 'The subdomain is not available');

            // instead use a new subdomain
            cy.get('#id_subdomain').clear().type(subdomain_2)
            cy.get('#id_subdomain').blur();
            cy.get('#div_id_subdomain').should('contain.text', 'The subdomain is available');
            // create the app
            cy.get('#submit-id-submit').contains('Submit').click()

            verifyAppStatus(app_name, "Running", "Creating", "Running", "project")

            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name_2).should('have.attr', 'href').and('include', subdomain_2)

            // Change subdomain of a previously created app
            cy.logf("Now changing subdomain of an already created app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains("Settings").click()
            cy.get('#id_subdomain').clear().type(subdomain_3)

            cy.get('#submit-id-submit').contains('Submit').click()
            // check that the app was updated with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain_3)

            // Verify that the app status is not Deleted (Deleting and Created ok)
            cy.get('tr:contains("' + app_name + '")').find('span').should('not.contain', 'Deleted')
            // Finally verify status equals Running
            verifyAppStatus(app_name, "Running", "Changing", "Running", "project") // TODO: Here. Fix this!

            // Wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name, "Running", "Changing", "Running", "project")
            })

            // Delete the first app
            cy.logf("Deleting the first app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // Delete the second app
            cy.logf("Deleting the second app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_2 + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_2 + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_2 + '")').should('not.exist')
            })



        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    // this test is skipped now because app statuses do not work as expected in the CI;
    // needs to be enabled when running against a running dev instance
    it("see correct statuses when deploying apps", {}, () => {

        //delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-subdomain-example", "e2e-deploy-app-test")
        deleteAppIfExists("e2e-second-subdomain-example", "e2e-deploy-app-test")

        // These tests are to check that the event listener works as expected

        const createResources = Cypress.env('create_resources');
        const project_name = "e2e-deploy-app-test"
        const app_name_statuses = "e2e-app-statuses"
        const app_description = "e2e-subdomain-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const app_type = "Custom App"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with project permissions
            cy.logf("Now creating an app with a non-existent image reference - expecting Image Error", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_statuses)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            cy.get('#id_port').type("8501")
            cy.get('#id_image').type("hkqxqxkhkqwxhkxwh") // input random string
            cy.get('#submit-id-submit').contains('Submit').click()
            // Check that the app was created. Using custom timeout of 5 secs
            cy.get('tr:contains("' + app_name_statuses + '")').find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Error: ErrImagePull')
            cy.logf("Now updating the app to give a correct image reference - expecting Running", Cypress.currentTest)
            cy.get('tr:contains("' + app_name_statuses + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_statuses + '")').find('a').contains('Settings').click()
            cy.get('#id_image').clear().type(image_name)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Using longer custom timeout for correct image to be set to Running
            verifyAppStatus(app_name_statuses, "Running", "Changing", "Running", "project")
            cy.get('tr:contains("' + app_name_statuses + '")', {timeout: longCmdTimeoutMs}).find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Running')

            // Delete the app
            cy.logf("Deleting the app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_statuses + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_statuses + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            // Verify deletion
            // Give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_statuses + '")').should('not.exist')
            })

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    after(() => {

            if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {

                cy.log("Cleaning up test data via Django endpoint");
                cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                cy.cleanupTestUser(TEST_USER_DATA);
            }

            cy.logf("End after() hook", Cypress.currentTest)
    })

})
