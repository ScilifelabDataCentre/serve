if (Cypress.env('create_resources') === true) {
    // All of these tests rely on creating resources

    describe("Test managing user app types", () => {

        // Fast UI checks; k8s assertions are optional.

        // Keep the default timeout short and opt into longer waits where needed.
        const defaultCmdTimeoutMs = 10000
        const longCmdTimeoutMs = 180000

        // Cypress env variables with default value
        let env_run_extended_k8s_checks

        // Function to verify the displayed app status and permission level
        // The expected values are tested if non-empty
        const verifyAppStatus = (
            app_name,
            expected_status,
            expected_permission,
            expected_latest_user_action) => {

            cy.get('tr:contains("' + app_name + '")', { timeout: longCmdTimeoutMs }).should('be.visible').then(($approw) => {
                // The status span element has id with format: status-customapp-nnn
                if (expected_status != "") {
                    cy.get($approw).find('[data-cy="appstatus"]', { timeout: longCmdTimeoutMs }).should('contain', expected_status)
                }

                if (expected_latest_user_action != "") {
                    cy.get($approw).find('[data-cy="appstatus"]').should('have.attr', 'data-app-action', expected_latest_user_action)
                }

                // The permission level span elment has id with format: permission-283
                if (expected_permission != "") {
                    cy.get($approw).find('[data-cy="app-permission"]').should('contain', expected_permission)
                }
            })
        };

        // user: e2e_tests_user_manage_apps_user
        let users
        let TEST_USER_DATA
        const TEST_USER_SUFFIX = "app-types"
        const TEST_PROJECT_DATA = {
            project_name: "e2e-user-manage-app-types-test-proj",
            project_description: "e2e-user-manage-app-types-test-proj-desc",
          };

        before({ defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            cy.logf("Begin before() hook", Cypress.currentTest)

            env_run_extended_k8s_checks = Cypress.env('run_extended_k8s_checks') ?? false

            cy.fixture('users.json').then(function (data) {
                users = data
                TEST_USER_DATA = {
                    ...data.user_manage_apps_user,
                    username: data.user_manage_apps_user.username + "-" + TEST_USER_SUFFIX,
                    email: data.user_manage_apps_user.email.replace("@", "+" + TEST_USER_SUFFIX + "@"),
                };
            })

            if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
                cy.log("Populating test data via Django endpoint");
                cy.fixture('users.json').then(function (data) {
                    TEST_USER_DATA = {
                        ...data.user_manage_apps_user,
                        username: data.user_manage_apps_user.username + "-" + TEST_USER_SUFFIX,
                        email: data.user_manage_apps_user.email.replace("@", "+" + TEST_USER_SUFFIX + "@"),
                    };
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
                // hmm, longer timeout here does not seem to have an impact
                cy.visit("/", {
                    timeout: 45000,
                    retryOnStatusCodeFailure: true,
                    retryOnNetworkFailure: true,
                })
                // seed the db with a user
                cy.logf("Running seed-user-manage-apps-user.py", Cypress.currentTest)
                cy.exec("./cypress/e2e/db-seed-user-manage-apps-user.sh")
                // username in fixture must match username in db-reset.sh
            }

            cy.wrap(null).then(() => {
                cy.loginViaApi(TEST_USER_DATA.email, TEST_USER_DATA.password)
            })

            cy.logf("End before() hook", Cypress.currentTest)
        })

        beforeEach(() => {
            cy.logf("Begin beforeEach() hook", Cypress.currentTest)

            // username in fixture must match username in db-reset.sh
            cy.logf("Logging in", Cypress.currentTest)
            cy.wrap(null).then(() => {
                cy.loginViaApi(TEST_USER_DATA.email, TEST_USER_DATA.password)
            })

            cy.logf("End beforeEach() hook", Cypress.currentTest)
        })

        it("can deploy a shiny app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of a public Shiny proxy app
            // TODO: We need to add a test here for validating Site-dir option. See SS-1206 for details
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-shiny-example"
            const app_description = "e2e-shiny-description"
            const source_code_url = "https://doi.org/example"
            const image_name = "ghcr.io/scilifelabdatacentre/shiny-adhd-medication-sweden:20240117-062031"
            const image_port = "3838"
            const app_type = "Shiny App"

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
            cy.get('#id_mount_path').should('exist')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // Though Shiny Proxy apps can take a long time to start
            // this is OK here because we only verify that it was created
            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            cy.logf("Checking that all shiny app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            cy.logf("Checking that the shiny app is displayed on the public apps page", Cypress.currentTest)
            cy.visit("/apps")
            cy.get('h4.card-title', { timeout: longCmdTimeoutMs }).should('contain', app_name)
            cy.get('.card-text').find('p').should('contain', app_description)

            cy.logf("Checking that instructions for running the app locally are displayed on public apps page", Cypress.currentTest)
            cy.get('a[data-bs-target="#dockerInfoModal"]').first().click()
            cy.get('div#dockerInfoModal').should('be.visible')
            cy.get('code').first().should('contain', image_name)
            cy.get('code').first().should('contain', image_port)
            cy.get('div.docker-info-modal-footer').find('button').contains('Close').click()

            cy.logf("Checking that source code URL is displayed on the public apps page", Cypress.currentTest)
            cy.visit("/apps")
            // Find the card with specific app name and owner
            cy.contains('h4.card-title', app_name, { timeout: longCmdTimeoutMs })
                .parents('.card')
                    .within(() => {
                        // Click the Details link
                        cy.get('a[id^="source-code-url"]').should('have.attr', 'href', source_code_url)
                    })
            // Verify that the public shiny app cannot be deleted (due to DOI protection)
            cy.logf("Verifying that the public shiny app cannot be deleted by regular users", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Verify that the app is still visible under public apps (since it wasn't deleted)
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name, { timeout: longCmdTimeoutMs }).should('exist')
        })

        it("can deploy a dash app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test to create and delete a Dash app
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-dash-example"
            const app_description = "e2e-dash-description"
            const source_code_url = "https://doi.org/example"
            const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
            const image_port = "8000"
            const app_type = "Dash App"
            const default_url_subpath = "default/url/subpath/"

            // Create Dash app
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()

            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            //cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click() // Go to Advanced settings
            cy.get('#id_default_url_subpath').clear().type(default_url_subpath) // provide default_url_subpath

            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            // The final app status and latest user action:
            // Wait for 5 seconds and check the app status again
            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name, "Running", "Public", "Creating")
                })
            }

            // Verify Dash app values by opening the app settings form
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)
            //cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click() // Go to Advanced settings
            cy.get('#id_default_url_subpath').should('have.value', default_url_subpath)

            // Verify that the public dash app cannot be deleted (due to DOI protection)
            cy.logf("Verifying that the public dash app cannot be deleted by regular users", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Verify that the app is still visible under public apps (since it wasn't deleted)
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name, { timeout: longCmdTimeoutMs }).should('exist')
        })

        it("can deploy a tissuumaps app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-tissuumaps-example"
            const app_description = "e2e-tissuumaps-description"
            const app_type = "TissUUmaps App"

            let volume_display_text = "project-vol (" + project_name + ")"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            cy.logf("Creating a tisuumaps app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_volume').select(volume_display_text)
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            // Wait for 5 seconds and check the app status again
            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name, "Running", "Public")
                })
            }

            cy.logf("Checking that all tissuumaps app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_volume').find(':selected').should('contain', 'project-vol')

            // Verify that the public tissuumaps app cannot be deleted (due to DOI protection)
            cy.logf("Verifying that the public tissuumaps app cannot be deleted by regular users", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Verify that the app is still visible under public apps (since it wasn't deleted)
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name, { timeout: longCmdTimeoutMs }).should('exist')
        })

        it("can deploy a gradio app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test to create and delete a Gradio app
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-gradio-example"
            const app_description = "e2e-gradio-description"
            const source_code_url = "https://doi.org/example"
            const image_name = "ghcr.io/scilifelabdatacentre/gradio-flower-classification:20241118-174426"
            const image_port = "7860"
            const app_type = "Gradio App"

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
            cy.get('#id_mount_path').should('exist')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            // Verify Gradio app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Verify that the public gradio app cannot be deleted (due to DOI protection)
            cy.logf("Verifying that the public gradio app cannot be deleted by regular users", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Verify that the app is still visible under public apps (since it wasn't deleted)
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name, { timeout: longCmdTimeoutMs }).should('exist')
        })

        it("can deploy a streamlit app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test to create and delete a Streamlit app
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-streamlit-example"
            const app_description = "e2e-streamlit-description"
            const source_code_url = "https://doi.org/example"
            const image_name = "ghcr.io/scilifelabdatacentre/streamlit-image-to-smiles:20241112-183549"
            const image_port = "8501"
            const app_type = "Streamlit App"

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
            cy.get('#id_mount_path').should('exist')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            // Verify Streamlit app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Verify that the public streamlit app cannot be deleted (due to DOI protection)
            cy.logf("Verifying that the public streamlit app cannot be deleted by regular users", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Verify that the app is still visible under public apps (since it wasn't deleted)
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name, { timeout: longCmdTimeoutMs }).should('exist')
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


}
