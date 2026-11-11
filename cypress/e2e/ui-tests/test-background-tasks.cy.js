if (Cypress.env('create_resources') === true) {
    // All of these tests rely on creating resources

    describe("Test background tasks", () => {

        // Fast UI checks; k8s assertions are optional.

        // Keep the default timeout short and opt into longer waits where needed.
        const defaultCmdTimeoutMs = 10000

        // timeout for background tasks
        const taskTimeoutMs = 60000

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

        // Find the target element with options
        // Use options argument to set timeout
        const stepDetail = (stepName, selector = '.step-detail-copy', options) =>
            cy.get('#step-list').contains('.step-row', stepName).find(selector, options)

        // Verify the text in the target element
        // chain is element querying.  e.g. cy.get()
        const expectText = (chain, expected) =>
            expected instanceof RegExp
                ? chain.should(($el) => expect($el.text()).to.match(expected))
                : chain.should('contain', expected)

        // Verify the UI transition of background tasks.
        // Skip verifying the initial displayed content if no initial argument is provided
        const expectStep = (stepName, { initial, final, selector = '.step-detail-copy'}) => {
            if (initial) {
                stepDetail(stepName).should('contain', initial)
            }
            expectText(stepDetail(stepName, selector, { timeout: taskTimeoutMs}), final)
        }

        // Constant to verify all background task steps
        const STEP_EXPECTATIONS = {
            imageAccess: {
                name: 'Check Image Access',
                success: {final: 'Completed successfully'}, // initial check for Image Access is flaky
                failure: {final: /Could not verify that container image|is not publicly pullable/}
            },
            imageCompatibility: {
                name: 'Check Image Compatibility',
                success: {initial: 'Currently running', final: 'Completed successfully'},
                failure: {initial: 'Currently running', final: 'Make sure the image is built for amd64', selector: '.step-detail-note'}
            },
            sourceCodeUrl: {
                name: 'Check Source Code URL',
                success: {initial: 'Currently running', final: 'Completed successfully'},
                skipped: {initial: 'Waiting for this step to start', final: 'Skipped: no source code URL'},
                failure: {initial: 'Check did not succeed', final: 'Source code URL unreachable'}
            },
            doi: {
                name: 'Reserve a Digital Object Identifier (DOI)',
                success: {initial: 'Currently running', final: 'Completed successfully'},
                skipped: {final: 'Skipped: A required deployment check failed earlier'}
            },
            deploy: {
                name: 'Deploy app',
                success: {initial: 'Waiting for app status', final: 'The app is running'},
                failure: {final: 'Deployment cannot continue until the failed required check is resolved'}
            }
        }

        // Function to verify background tasks
        // Verify that all background tasks succeed when no arguments are provided
        const verifyBackgroundTasks = (outcomes = {}) => {
            cy.logf("Checking background tasks progress", Cypress.currentTest)
            Object.entries(STEP_EXPECTATIONS).forEach(([key, step]) => {
                // default scenario is success
                const outcome = outcomes[key] ?? 'success'
                // it skips the step if the argument value is 'ignore' e.g. {sourceCodeUrl: 'ignore'}
                if (outcome === 'ignore') return
                const expectation = step[outcome]
                if (!expectation) {
                    throw new Error(`Unknown outcome "${outcome}" for step "${key}"`)
                }
                expectStep(step.name, expectation)
            })
        }

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

        it("displays the correct status indicators when background tasks succeed with public visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
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
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            //// Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks()

            // Verify that it redirects to the detail page after the deployment is completed
            cy.logf("Checking it redirects to the app detail page", Cypress.currentTest)
            cy.location('pathname', { timeout: 60000 })
                .should('include', '/apps/details/')
            cy.get('h1').should('contain', app_name)
            cy.get('#deployment-message').should('contain', 'The app is running')
        })

        it("displays the correct status indicators when background tasks succeed with project visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
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
            cy.selectAppVisibility('project')
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks()
        })

        it("displays the correct status indicators when background tasks succeed with link visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:240312-1531"
            const image_port = "8501"
            const app_type = "Custom App"
            const reason = "testing"
            const app_source_code_public = "https://source.org/"


            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with public permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('link')
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_note_on_linkonly_privacy').clear().type(reason)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks()
        })

        it("displays the correct status indicators when background tasks succeed with private visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
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
            cy.selectAppVisibility('private')
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks()
        })

        it("displays that source URL checking is skipped with project visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:240312-1531"
            const image_port = "8501"
            const app_type = "Custom App"


            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with public permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('project')
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks({sourceCodeUrl: 'skipped'})
        })

        it("displays that source URL checking is skipped with link visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:240312-1531"
            const image_port = "8501"
            const app_type = "Custom App"
            const reason = "testing"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with public permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('link')
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_note_on_linkonly_privacy').clear().type(reason)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks({sourceCodeUrl: 'skipped'})
        })

        it("displays that source URL checking is skipped with private visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:240312-1531"
            const image_port = "8501"
            const app_type = "Custom App"


            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with public permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('private')
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks({sourceCodeUrl: 'skipped'})
        })

        it("displays the correct status indicators when image compatibility checking fails", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_description = "e2e-custom-description"
            const image_name = "docker.io/arm64v8/alpine:3.24.4" // this image is for linux/arm64/v8
            const image_port = "8501"
            const app_type = "Custom App"
            const app_source_code_public = "https://source.org/"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with project permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.selectAppVisibility('public')
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            // Verify that the background task progress is displayed correctly.
            verifyBackgroundTasks({
                imageCompatibility: 'failure',
                doi: 'skipped',
                deploy: 'failure'
            })
        })

        it("displays the correct status indicators when source URL checking fails", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
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
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.submitAppForm()

            verifyBackgroundTasks({
                sourceCodeUrl: 'failure',
                doi: 'skipped',
                deploy: 'failure'
            })
        })

        it("displays only saving metadata task with draft visibility", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            // Test of background tasks
            // Names of objects to create
            const project_name = TEST_PROJECT_DATA.project_name
            const app_name = "e2e-custom-example"
            const app_type = "Custom App"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with public permissions
            cy.logf("Creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.selectAppVisibility('public')
            cy.get('button').contains('Save draft')
                .should('exist').click()

            // Verify that the background task progress is displayed correctly.
            cy.logf("Checking background tasks progress", Cypress.currentTest)
            cy.get('#step-list').contains('.step-row', 'Save draft metadata')
                .find('.step-detail-copy')
                .should('contain', 'Currently running')
            cy.get('#step-list').contains('.step-row', 'Save draft metadata')
                .find('.step-detail-copy', { timeout: 60000 })
                .should('contain', 'Completed successfully')

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
