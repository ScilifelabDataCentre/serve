if (Cypress.env('create_resources') === true) {
    // All of these tests rely on creating resources

    describe("Test managing user app", () => {

        // Tests performed as an authenticated user that creates and deletes apps.
        // Note that these tests are meant to be relatively fast running UI tests
        // and therefore do not wait for results from k8s.
        // For tests involving k8s, see integration tests.

        // The default command timeout should not be so long
        // Instead use longer timeouts on specific commands where deemed necessary and valid
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
        const TEST_PROJECT_DATA = {
            project_name: "e2e-user-manage-apps-test-proj",
            project_description: "e2e-user-manage-apps-test-proj-desc",
          };

        before({ defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            cy.logf("Begin before() hook", Cypress.currentTest)

            env_run_extended_k8s_checks = Cypress.env('run_extended_k8s_checks') ?? false

            if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
                cy.log("Populating test data via Django endpoint");
                cy.fixture('users.json').then(function (data) {
                    TEST_USER_DATA = data.user_manage_apps_user;
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

            cy.fixture('users.json').then(function (data) {
                users = data
                cy.loginViaApi(users.user_manage_apps_user.email, users.user_manage_apps_user.password)
            })

            cy.logf("End before() hook", Cypress.currentTest)
        })

        beforeEach(() => {
            cy.logf("Begin beforeEach() hook", Cypress.currentTest)

            // username in fixture must match username in db-reset.sh
            cy.logf("Logging in", Cypress.currentTest)
            cy.fixture('users.json').then(function (data) {
                users = data

                cy.loginViaApi(users.user_manage_apps_user.email, users.user_manage_apps_user.password)
            })

            cy.logf("End beforeEach() hook", Cypress.currentTest)
        })

        it("can deploy a project and public app using the custom app chart", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // This test creates two custom apps and also modifies and tests the permission levels
            // Names of objects to create
            const project_name = "e2e-user-manage-apps-test-proj"
            const app_name_project = "e2e-custom-example-project"
            const app_name_public = "e2e-custom-example-public"
            const app_name_public_2 = "e2e-custom-example-2-public"
            const app_description = "e2e-custom-description"
            const app_description_2 = "e2e-custom-2-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
            const image_name_2 = "ghcr.io/scilifelabdatacentre/example-streamlit:230921-1443"
            const image_port = "8501"
            const image_port_2 = "8502"
            const mount_path_2 = "/srv/shiny-server/data"
            const link_privacy_type_note = "some-text-on-link-only-app"
            const app_type = "Custom App"
            const app_source_code_public = "https://doi.org/example"
            const default_url_subpath = "default/url/subpath/"
            const changed_default_url_subpath = "changed/subpath/"
            const invalid_default_url_subpath = "€% / ()"
            const keyword = "Microscopy"

            const mount_path = "/home/data"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with project permissions
            cy.logf("Now creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_project)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#id_mount_path').select(mount_path+ " (project-vol (" + project_name + "))")

            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            //cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').clear().type(default_url_subpath) // provide default_url_subpath
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Wait for the app row to appear or log form errors if not
            cy.get('body').then(($body) => {
                if ($body.find('tr:contains("' + app_name_project + '")').length === 0) {
                    // If the row is not present, check for form errors
                    if ($body.find('.alert-danger, .errorlist').length > 0) {
                        cy.log('Form errors: ' + $body.find('.alert-danger, .errorlist').text())
                    }
                }
            })
            cy.get('tr:contains("' + app_name_project + '")', { timeout: 10000 }).should('be.visible')
            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name_project, "Creating", "Project", "Creating")

            // check that the default URL subpath was created
            cy.contains('a', app_name_project)
                .should('have.attr', 'href')
                .and('include', default_url_subpath)
            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name_project).should('not.exist')

            // make this app public as an update and check that it works
            cy.logf("Now making the project app public", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_project + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_project + '")').find('a').contains('Settings').click()
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.get('#div_id_invenio_tags').should('be.visible')
                .within(() => {
                    cy.get('input[placeholder*="Start typing"]').should('be.visible').type(keyword)
                    cy.get('.dropdown-menu .dropdown-item', { timeout: 10000 }).should('be.visible').first().should('have.text', keyword).click()
                })
            // make sure that the extra fields for public apps are visible and work
            cy.get('#id_language').should('be.visible').within(() => {
                cy.get('option').eq(0).should('have.value', 'eng').and('contain', 'English')
                cy.get('option').eq(1).should('have.value', 'swe').and('contain', 'Swedish')
                cy.get('option').eq(2).should('have.value', 'und').and('contain', 'Other')
            })
            cy.contains('button', 'Add creator').should('be.visible').click()
            cy.contains('.modal-content', 'Add creator').should('be.visible')
                .within(() => {
                    cy.get('#newCreatorName').should('be.visible')
                    cy.get('#newCreatorLastName').should('be.visible')
                    cy.get('#newCreatorAffiliation').should('be.visible')
                    cy.get('#newCreatorOrcid').should('be.visible')
                    cy.get('#saveAndAddAnotherCreatorBtn').should('be.disabled')
                    cy.get('#saveCreatorBtn').should('be.disabled')
                })
            cy.get('#creatorsModal .btn-close').should('be.visible').click()
            cy.get('#creatorsModal').should('not.be.visible')
            cy.get('#addFunderBtn').should('be.visible').click()
            cy.contains('.modal-content', 'Add funder').should('be.visible')
                .within(() => {
                    cy.get('#funderNameInput').should('be.visible')
                    cy.get('#awardNumberInput').should('be.visible')
                    cy.get('#awardTitleInput').should('be.visible')
                    cy.get('#awardUrlInput').should('be.visible')
                    cy.get('#saveAndAddAnotherBtn').should('be.disabled')
                    cy.get('#saveFunderBtn').should('be.disabled')
                })
            cy.get('#funderModal .btn-close').should('be.visible').click()
            cy.get('#funderModal').should('not.be.visible')
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // We now verify the correct permission level and user action
            // but not the app status because it is dependent on k8s
            verifyAppStatus(app_name_project, "", "Public", "Changing")

            // Wait for 5 seconds and check the app status again
            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name_project, "Running", "Public", "Changing")
                })
            }

            // Verify that the public app cannot be deleted (due to DOI protection)
            cy.logf("Verifying that the public app cannot be deleted by regular users", Cypress.currentTest)

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name_project + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_project + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Create a public app and verify that it is displayed on the public apps page
            cy.logf("Now creating a public app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_public)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_mount_path').select(mount_path+ " (project-vol (" + project_name + "))")
            //cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').clear().type(default_url_subpath) // provide default_url_subpath
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name_public, "Creating", "Public", "Creating")

            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                // Wait for 5 seconds and check the app status again
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name_public, "Running", "Public", "Creating")
                })
            }

            // check that the default URL subpath was created
            cy.contains('a', app_name_public)
                .should('have.attr', 'href')
                .and('include', default_url_subpath);

            cy.visit("/apps")
            cy.get('h4.card-title', { timeout: longCmdTimeoutMs }).should('contain', app_name_public)
            cy.get('.card-text').find('p').should('contain', app_description)

            // Check that the public app is displayed on the homepage
            cy.logf("Now checking if the public app is displayed when not logged in.", Cypress.currentTest)
            cy.visit("/home/")
            cy.get('h4').should('contain', app_name_public)

            // Log out and check that the public app is still displayed on the homepage
            cy.clearCookies();
            cy.clearLocalStorage();
            Cypress.session.clearAllSavedSessions()
            cy.visit('/projects/')
            cy.get('h3').should('contain', 'Login required') // check that logout worked
            cy.visit("/")
            cy.get('h4').should('contain', app_name_public)
            // Log back in
            cy.fixture('users.json').then(function (data) {
                users = data
                cy.loginViaUI(users.user_manage_apps_user.email, users.user_manage_apps_user.password)
            })

            // Check that the logs page opens for the app
            cy.logf("Now checking that the logs page for the app opens", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_public + '")').should('be.visible').find('a').contains('Logs').click()
            cy.get('h3').should('contain', "Logs")

            // Try changing the name, description, etc. of the app and verify it works
            cy.logf("Now changing the name and description of the public app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_public + '")').should('be.visible').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_public) // name should be same as before
            cy.get('#id_name').clear().type(app_name_public_2) // now change name
            cy.get('#id_description').should('have.value', app_description) // description should be same as set before
            cy.get('#id_description').clear().type(app_description_2) // now change description
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            // Note: DOI-protected public apps cannot change their access level
            // Verify that the access field is disabled due to DOI protection
            cy.get('#id_access').should('be.disabled')
            // /home/data (project-vol (e2e-user-manage-apps-test-proj))
            cy.get('#id_mount_path').find(':selected').should('contain', mount_path + " (project-vol (" + project_name + "))")
            cy.get('#id_port').should('have.value', image_port)
            cy.get('#id_port').clear().type(image_port_2)
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_image').clear().type(image_name_2)
            cy.get('#id_mount_path').find(':selected').should('contain', mount_path + " (project-vol (" + project_name + "))")
            cy.get('#id_mount_path').select(mount_path_2 + " (project-vol (" + project_name + "))")
            //cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').should('have.value', default_url_subpath) // default_url_subpath should be same as before
            cy.get('#id_default_url_subpath').clear().type(changed_default_url_subpath) // provide changed_default_url_subpath
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // We do not verify the app status because it depends on k8s
            // Note: Access level remains 'Public' due to DOI protection
            verifyAppStatus(app_name_public_2, "", "Public", "Changing")

            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                // NB: it will get status "Running" but it won't work because the new port is incorrect
                verifyAppStatus(app_name_public_2, "Running", "Public", "Changing")

                // Wait for 5 seconds and check the app status again
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name_public_2, "Running", "Public", "Changing")
                })
            }

            // check that the default URL subpath was changed
            cy.contains('a', app_name_public_2)
                .should('have.attr', 'href')
                .and('include', changed_default_url_subpath);

            // Check that the changes were saved
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_public_2)
            cy.get('#id_description').should('have.value', app_description_2)
            // Note: Access level remains 'Public' due to DOI protection
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_port').should('have.value', image_port_2)
            cy.get('#id_image').should('have.value', image_name_2)
            cy.get('#id_mount_path').find(':selected').should('contain', mount_path_2 + " (project-vol (" + project_name + "))")
            //cy.get('button.accordion-button.collapsed[data-bs-target="#advanced-settings"]').click(); // Go to Advanced settings
            cy.get('#id_default_url_subpath').should('have.value', changed_default_url_subpath) // changed_url_subpath should be same as before

            // Make sure that giving invalid input in default_url_subpath field results in an error
            cy.get('#id_default_url_subpath').clear().type(invalid_default_url_subpath) // provide invalid_default_url_subpath
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click() // this should trigger the error
            cy.completeAppSubmissionFlow()

            // check this invalid_default_url_subpath error was matched
            cy.get('.client-validation-feedback.client-validation-invalid')
                .should('exist')
                .and('include.text', 'Your custom URL subpath is not valid, please correct it');

            // Verify that the created public app cannot be deleted (due to DOI protection)
            cy.logf("Now verifying that the public app cannot be deleted by regular users", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name_public_2 + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Note: Public apps with DOI protection remain in the system and cannot be deleted by regular users
            // This is the intended behavior to protect published research outputs

            // Verify that the app is still visible under public apps (since it wasn't deleted)
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name_public_2, { timeout: longCmdTimeoutMs }).should('exist')
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
