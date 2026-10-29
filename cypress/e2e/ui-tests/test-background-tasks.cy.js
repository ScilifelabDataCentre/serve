if (Cypress.env('create_resources') === true) {
    // All of these tests rely on creating resources

    describe("Test background tasks", () => {

        // Fast UI checks; k8s assertions are optional.

        // Keep the default timeout short and opt into longer waits where needed.
        const defaultCmdTimeoutMs = 10000
        const longCmdTimeoutMs = 180000

        // Cypress env variables with default value
        let env_run_extended_k8s_checks

        // user: e2e_tests_user_manage_apps_user
        let users
        let TEST_USER_DATA
        const TEST_USER_SUFFIX = "app-types"
        const TEST_PROJECT_DATA = {
            project_name: "e2e-user-background-tasks-test-proj",
            project_description: "e2e-user-background-tasks-test-proj-desc",
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

        it("can redirect when a deployment finished", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:240312-1531"
            const image_port = "8501"
            const app_type = "Custom App"
            const app_source_code_public = "https://source.org/"


            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with public permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('public')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
           
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            cy.logf("Checking background tasks progress", Cypress.currentTest)
            cy.url().should('contain', 'apps/progress/')
            cy.get('#progress-pill').should('contain', 'Checking')
            cy.get('#progress-bar').should('exist')
            cy.get('#step-list').contains('Deploy app').should('exist')
            cy.get('#details-link').should('contain', 'Deployment summary')

            // Verify that progress information is changed on the UI
            cy.logf("Checking the displayed information changes as the task progress", Cypress.currentTest)
            cy.get('#progress-pill', { timeout: 180000 }).should('contain', 'Ready')
            cy.get('#progress-bar').should('have.class', 'bg-success')
            
            // Verify that it redirects to the detail page after the deployment is completed
            cy.logf("Checking it redirects to the app detail page", Cypress.currentTest)
            cy.location('pathname', { timeout: 60000 })
                .should('include', '/apps/details/')
            cy.get('h1').should('contain', app_name)
            cy.get('#deployment-message').should('contain', 'The app is running')
        })

        it("does not redirect when a deployment failed", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
            const image_port = "8501"
            const app_type = "Custom App"
            const app_source_code_public = "https://fake.source.com/"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with project permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('public')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            cy.logf("Checking background tasks progress", Cypress.currentTest)
            cy.url().should('contain', 'apps/progress/')
            cy.get('#progress-pill').should('contain', 'Checking')
            cy.get('#progress-bar').should('exist')
            cy.get('#step-list').contains('Deploy app').should('exist')
            cy.get('#details-link').should('contain', 'Deployment summary')
            cy.get('#progress-pill', { timeout: 120000 }).should('contain', 'Attention needed')
            
            // Verify that it doesn't redirect to the detail page after the deployment is failed
            cy.logf("Checking it doesn't redirect to the app detail page", Cypress.currentTest)
            cy.location('pathname').then((initialPath) => {
                cy.wait(3000)
                cy.location('pathname').should('eq', initialPath)
            })

            // Verify that progress information is changed on the UI
            cy.logf("Checking the displayed information changes as the task progress", Cypress.currentTest)
            cy.get('h1').should('contain', 'We could not finish preparing your app')
            cy.get('#progress-inline')
                .should('contain', '2 steps need attention')
            cy.get('#progress-message')
                .should('contain', 'Deployment cannot continue until the failed required check is resolved')
            cy.get('#progress-bar').should('have.class', 'bg-danger')
            cy.get('#step-list').contains('.step-row', 'Check Source Code URL')
                .should('contain', 'Failed')
                .next()
                .should('contain', 'Skipped')
            cy.get('#step-list').contains('.step-row', 'Deploy app')
                .should('contain', 'Failed')
        })

        it("can redirect when draft data is saved", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
            const image_port = "8501"
            const app_type = "Custom App"
            const app_source_code_public = "https://source.org/"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with public permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('public')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.get('button').contains('Save draft')
                .should('be.visible').click()

            // Verify that the background task progress is displayed correctly.
            cy.logf("Checking background tasks progress", Cypress.currentTest)
            cy.url().should('contain', 'apps/progress/')
            cy.get('#progress-pill').should('contain', 'Saving')
            cy.get('#progress-bar').should('exist')
            cy.get('#step-list').contains('Save draft metadata').should('exist')
            cy.get('a').contains('Return to project').should('exist')

            // Verify that progress information is changed on the UI
            cy.logf("Checking the displayed information changes as the task progress", Cypress.currentTest)
            cy.get('#progress-pill', { timeout: 120000 }).should('contain', 'Saved')
            cy.get('#progress-bar').should('have.class', 'bg-success')

            // Verify that it redirects to the project page after draft data is saved
            cy.logf("Checking it redirects to the project page", Cypress.currentTest)
            cy.location('pathname', { timeout: 60000 })
                .should('include', '/projects/' + project_name)
            cy.get('h3').should('contain', project_name)
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
