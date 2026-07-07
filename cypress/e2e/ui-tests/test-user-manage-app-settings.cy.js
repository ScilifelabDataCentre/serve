if (Cypress.env('create_resources') === true) {
    // All of these tests rely on creating resources

    describe("Test managing user app settings", () => {

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
        const TEST_USER_SUFFIX = "app-settings"
        const TEST_PROJECT_DATA = {
            project_name: "e2e-user-manage-app-settings-test-proj",
            project_description: "e2e-user-manage-app-settings-test-proj-desc",
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

        it("can modify app settings resulting in NO k8s redeployment shows correct app status", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // An advanced test to verify user can modify app settings such as the name and description
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-change-app-settings-no-redeploy"
            const app_name_edited = app_name + "-edited"
            const app_description = "e2e-change-app-settings-description"
            const source_code_url = "https://doi.org/example"
            const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
            const image_port = "8000"
            const app_type = "Dash App"

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
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            // Verify Dash app values
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

            // Edit Dash app: modify the app name and description
            cy.logf("Editing the dash app settings (non redeployment fields)", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').should('be.visible').find('a').contains('Settings').click()
            // Here we change the app name from app_name to app_name_edited
            cy.get('#id_name').type("-edited")
            cy.get('#id_description').type(", edited description.")
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            // Verify that the app status by checking latest user action:
            verifyAppStatus(app_name_edited, "", "Public", "Changing")

            // The final app status and latest user action:
            // Wait for 5 seconds and check the app status again
            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name_edited, "Running", "Public", "Creating")
                })
            }

            // Verify that the public dash app cannot be deleted (due to DOI protection)
            cy.logf("Verifying that the public dash app cannot be deleted by regular users", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Verify that the delete button is not available for public apps
            cy.get('tr:contains("' + app_name_edited + '")').should('be.visible').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_edited + '")').should('be.visible').find('a.confirm-delete').should('not.exist')

            // Click elsewhere to close the dropdown menu
            cy.get('body').click()

            // Verify that the app is still visible under public apps (since it wasn't deleted)
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name_edited, { timeout: longCmdTimeoutMs }).should('exist')
        })

        it("can modify app settings resulting in k8s redeployment shows correct app status", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // An advanced test to verify user can modify app settings resulting in k8s redeployment (image)
            // still shows the correct app status.
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-change-app-settings-redeploy"
            const app_description = "e2e-change-app-settings-description"
            const source_code_url = "https://doi.org/example"
            const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
            const image_port = "8000"
            const app_type = "Dash App"

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
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            // Verify Dash app values
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

            // Edit Dash app: modify the app image to an invalid or empty image
            cy.logf("Editing the dash app settings field Image to an invalid value", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_image').clear()
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Stay on the Settings page
            cy.url().should("include", "/apps/settings")

            // Edit Dash app: modify the app image back to a valid image
            cy.logf("Editing the dash app settings field Image to a valid value", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_image').clear().type(image_name)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            verifyAppStatus(app_name, "", "Public", "Changing")

            // The final app status and latest user action:
            // Wait for 5 seconds and check the app status again
            // This relies on the k8s event listener
            // Verify that the app status now equals Running
            if (env_run_extended_k8s_checks === true) {
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name, "Running", "Public", "Changing")
                })

                // Wait for 5 seconds and check the app status again
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name, "Running", "Public", "Changing")
                })
            }

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

        it("can set and change subdomain", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // A test to verify creating an app and changing the subdomain
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-subdomain-change"
            const app_description = "e2e-subdomain-change-description"
            const source_code_url = "https://doi.org/example"
            const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
            const image_port = "8000"
            const app_type = "Dash App"
            const subdomain_change = "subdomain-change"

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
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "Public", "Creating")

            // Verify Dash app values
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

            // Edit Dash app: change the suibdomain to a custom value
            cy.logf("Editing the dash app settings field subdomain", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_subdomain').clear().type(subdomain_change)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            // Back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name);

            // Verify that the app latest user action
            verifyAppStatus(app_name, "", "Public", "Changing")

            // Wait for 5 seconds and check the app status again
            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name, "Running", "Public", "Changing")
                })
            }

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

        it("can set and change custom subdomain several times", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // An advanced test to verify creating apps and changing subdomains. Steps taken:
            // 1. Create app e2e-subdomain-example, subdomain=subdomain-test
            // 2. Attempt create app e2e-second-subdomain-example, using subdomain=subdomain-test
            // 3. Create app e2e-second-subdomain-example, subdomain=subdomain-test2
            // 4. Change the subdomain of the first app to subdomain=subdomain-test3
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-subdomain-example"
            const app_name_2 = "e2e-second-subdomain-example"
            const app_description = "e2e-subdomain-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
            const app_type = "Custom App"
            const subdomain = "subdomain-test"
            const subdomain_2 = "subdomain-test2"
            const subdomain_3 = "subdomain-test3"

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
            cy.get('#id_mount_path').select("/home/data (project-vol (e2e-user-manage-app-settings-test-proj))")
            // fill out subdomain field
            cy.get('#id_subdomain').clear().type(subdomain)

            // create the app
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name, "Creating", "", "Creating")

            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain)

            // Try using the same subdomain the second time
            cy.logf("Now trying to create an app with an already taken subdomain", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()

            cy.get('#id_name').clear().type(app_name_2)
            cy.get('#id_description').clear().type(app_description)
            cy.get('#id_port').clear().type("8501")
            cy.get('#id_image').clear().type(image_name)

            // fill out subdomain field
            cy.get('#id_subdomain').clear().type(subdomain)
            cy.get('#id_subdomain').blur();
            cy.get('#div_id_subdomain').should('contain.text', 'The subdomain is not available');

            // instead use a new subdomain
            cy.get('#id_subdomain').clear().type(subdomain_2)
            cy.get('#id_subdomain').blur();
            cy.get('#div_id_subdomain').should('contain.text', 'The subdomain is available');
            // create the app
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // Check that the app was created and verify the app status
            // The initial app status and latest user action:
            verifyAppStatus(app_name_2, "Creating", "", "Creating")

            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name_2).should('have.attr', 'href').and('include', subdomain_2)

            // Change subdomain of a previously created app
            cy.logf("Now changing subdomain of an already created app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains("Settings").click()
            cy.get('#id_subdomain').clear().type(subdomain_3)

            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            cy.get('tr:contains("' + app_name + '")').should('be.visible')

            // Verify updated subdomain/action.
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain_3)
            verifyAppStatus(app_name, "", "", "Changing")

            // The final app status and latest user action:
            // Wait for 5 seconds and check the app status again
            // This relies on the k8s event listener
            if (env_run_extended_k8s_checks === true) {
                cy.wait(5000).then(() => {
                    verifyAppStatus(app_name, "Running", "", "Changing")
                })
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


}
