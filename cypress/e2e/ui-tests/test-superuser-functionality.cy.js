describe("Test superuser access", () => {

    // The longer timeout is often used when waiting for k8s operations to complete
    const longCmdTimeoutMs = 180000

    // Function to verify the displayed app status and permission level
    // The expected values are tested if non-empty
    const verifyAppStatus = (
        app_name,
        expected_status,
        expected_permission,
        expected_latest_user_action) => {

        cy.get('tr:contains("' + app_name + '")').should('be.visible').then(($approw) => {
            // The status span element has id with format: status-customapp-nnn
            if (expected_status != "") {
                cy.get($approw).find('[data-cy="appstatus"]').should('contain', expected_status)
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

    // Tests performed as an authenticated user that has superuser privileges
    // user: no-reply-superuser@scilifelab.se
    let users
    let TEST_SUPER_USER_DATA
    let TEST_USER_DATA
    const TEST_PROJECT_DATA = {
        project_name: "e2e-superuser-testuser-proj-test",
        project_description: "Description by regular user",
      };

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest)

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Populating test data via Django endpoint");
            const TEST_APP_DATA = {
                app_slug: "jupyter-lab",
                name: "Regular user's private app",
                access: "private",
                volume: null,
              };

            cy.fixture('users.json').then(function (data) {
                TEST_SUPER_USER_DATA = data.superuser;
                TEST_USER_DATA = data.superuser_testuser;
                cy.populateTestSuperUser(TEST_SUPER_USER_DATA);
                cy.populateTestUser(TEST_USER_DATA);
                cy.populateTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                cy.populateTestApp(TEST_USER_DATA, TEST_PROJECT_DATA, TEST_APP_DATA);
            });
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
            cy.logf("Running seed_superuser.py", Cypress.currentTest)
            cy.exec("./cypress/e2e/db-seed-superuser.sh")
        }

        cy.logf("End before() hook", Cypress.currentTest)
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)

        // email in fixture must match email in db-reset.sh
        cy.logf("Logging in as superuser", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.superuser.email, users.superuser.password)
        })

        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("can see extra deployment options and extra settings in a project", () => {
        // Names of objects to create
        const project_name = "e2e-create-default-proj-test"
        const project_description = "A test project created by an e2e test."
        const project_description_duplicate = "A test project with an existing project name"
        const project_description_2 = "An alternative project description created by an e2e test."

        cy.visit("/projects/")
        cy.get("title").should("have.text", "My projects | SciLifeLab Serve (beta)")

        cy.logf("Creating a project as a superuser", Cypress.currentTest)
        // Click button for UI to create a new project
        cy.get("a").should('be.visible').contains('New project').click()
        cy.url().should("include", "projects/templates")
        cy.get('h3').should('contain', 'New project')

        // Next click button to create a new blank project
        cy.get("a").should('be.visible').contains('Create').first().click()
        cy.url().should("include", "projects/create/?template=")
        cy.get('h3').should('contain', 'New project')

        // Fill in the options for creating a new blank project
        cy.get('input[name=name]').type(project_name)
        cy.get('textarea[name=description]').type(project_description)
        cy.get("input[name=save]").should('be.visible').contains('Create project').click()

        cy.get('h3', {timeout: longCmdTimeoutMs}).should('contain', project_name)
        cy.get('.card-text').should('contain', project_description)

        cy.logf("Checking that project settings are available", Cypress.currentTest)
        cy.get('[data-cy="settings"]').should('be.visible').click()
        cy.url().should("include", "settings")
        cy.get('h3').should('contain', 'Project settings')

        cy.logf("Checking that the correct project settings are visible (i.e. with extra settings)", Cypress.currentTest)
        cy.get('.list-group').find('a').should('contain', 'Access')
        cy.get('.list-group').find('a').should('contain', 'Flavors')
        cy.get('.list-group').find('a').should('contain', 'Environments')

        cy.logf("Changing project description", Cypress.currentTest)
        cy.get('textarea[name=description]').clear().type(project_description_2)
        cy.get('button').should('be.visible').contains('Save').click()
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('.card-text').should('contain', project_description_2)

        cy.logf("Check that creating another project with same existing project name will work for a superuser", Cypress.currentTest)
        cy.visit("/projects/")
        cy.get("a").should('be.visible').contains('New project').click()
        cy.get("a").should('be.visible').contains('Create').first().click()
        cy.get('input[name=name]').type(project_name) // this name already exists
        cy.get('textarea[name=description]').type(project_description_duplicate) // this will be used to ensure to delete it
        cy.get("input[name=save]").should('be.visible').contains('Create project').click()
        cy.get('h3', {timeout: longCmdTimeoutMs}).should('contain', project_name)
        cy.get('.card-text').should('contain', project_description_duplicate) // checking that project creation succeeded
        // deleting the project with the duplicate name
        cy.get('[data-cy="settings"]').should('be.visible').click()
        cy.get('a').should('be.visible').contains("Delete").click()
        .then((href) => {
            cy.get('div#delete').should('have.css', 'display', 'block')
            cy.get('#id_delete_button').should('be.visible').parent().parent().find('button').contains('Delete').click()
            .then((href) => {
                cy.get('div#deleteModal').should('have.css', 'display', 'block')
                cy.get('div#deleteModal').should('be.visible').find('button').contains('Confirm').click()
            })
        // checking that the project with the duplicate name has been deleted
        cy.visit("/projects/")
        cy.contains(project_description_duplicate).should('not.exist')
         })
        // going to the previously created project's page
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a.btn').contains('Open').click()

        cy.logf("Deleting the project from the settings menu", Cypress.currentTest)
        cy.get('[data-cy="settings"]').should('be.visible').click()
        cy.get('a').contains("Delete").should('be.visible').click()
        .then((href) => {
            cy.get('div#delete').should('have.css', 'display', 'block')
            cy.get('#id_delete_button').should('be.visible').parent().parent().find('button').contains('Delete').click()
            .then((href) => {
                cy.get('div#deleteModal').should('have.css', 'display', 'block')
                cy.get('div#deleteModal').should('be.visible').find('button').contains('Confirm').click()
            })
        cy.visit("/projects/")
        cy.contains(project_name).should('not.exist')

        })
    })

    it("can see and manipulate other users' projects and apps", () => {

        // Names of objects
        const project_name = "e2e-superuser-testuser-proj-test" // from seed_superuser.py
        const project_description ="Description by regular user" // from seed_superuser.py
        const project_description_2 = "An alternative project description created by an e2e test."
        const private_app_name = "Regular user's private app" // from seed_superuser.py
        const private_app_name_2 = "App renamed by superuser"

        cy.logf("Verifying that a project of a regular user is visible", Cypress.currentTest)
        cy.visit("/projects/")
        cy.get('h5.card-title').should('contain', project_name)

        cy.logf("Verifying that can edit the description of a project of a regular user", Cypress.currentTest)
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('.card-text').should('contain', project_description)
        cy.get('[data-cy="settings"]').should('be.visible').click()
        cy.get('textarea[name=description]').clear().type(project_description_2)
        cy.get('button').should('be.visible').contains('Save').click()
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('.card-text').should('contain', project_description_2)

        cy.logf("Verifying that a private app of a regular user is visible", Cypress.currentTest)
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('tr:contains("' + private_app_name + '")').should('exist') // regular user's private app visible

        cy.logf("Verifying that can edit the private app of a regular user", Cypress.currentTest)
        cy.get('tr:contains("' + private_app_name + '")').should('be.visible').find('i.bi-three-dots-vertical').click()
        cy.get('tr:contains("' + private_app_name + '")').should('be.visible').find('a').contains('Settings').click()
        cy.get('#id_name').clear().type(private_app_name_2) // change name
        cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
        cy.get('tr:contains("' + private_app_name_2 + '")').should('exist') // regular user's private app now has a different name

        // Check that the app is visible and verify the app status
        verifyAppStatus(private_app_name_2, "", "private", "Changing")

        // Delete the app
        cy.logf("Deleting a regular user's private app", Cypress.currentTest)
        cy.get('tr:contains("' + private_app_name_2 + '")').should('be.visible').find('i.bi-three-dots-vertical').click()
        cy.get('tr:contains("' + private_app_name_2 + '")').should('be.visible').find('a.confirm-delete').click()
        cy.get('#modalConfirmDelete')
            .should('be.visible')
            .find('[data-cy="delete-app-button-confirm"]')
            .click()

        // Give the action some time after the click event
        cy.wait(2000).then(() => {
            // verify that the app is not visible in the project overview
                cy.get('tr:contains("' + private_app_name_2 + '")').should('not.exist')
        })

        // cy.get('tr:contains("' + private_app_name_2 + '")', {timeout: longCmdTimeoutMs}).find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Deleted')

        cy.logf("Deleting a regular user's project", Cypress.currentTest)
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').should('be.visible').find('button').contains('Delete').click()
               })
            })

    })

    it("can create a new flavor or environment and a regular user can subsequently use those", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-proj-flavor-env-test"
        const new_flavor_name = "4 CPU, 8 GB RAM"
        const new_flavor_name_unused = "Unused flavor"
        const new_environment_name = "e2e test environment"
        const new_environment_name_unused = "Unused environment"

        cy.logf("Logging in as a regular user and creating a project", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaUI(users.superuser_testuser.email, users.superuser_testuser.password)
        })
        cy.visit("/projects/")
        cy.get("a").should('be.visible').contains('New project').click()
        cy.get("a").should('be.visible').contains('Create').first().click()
        cy.get('input[name=name]').type(project_name)
        cy.get("input[name=save]").should('be.visible').contains('Create project').click()
        cy.get('h3').should('contain', project_name)

        Cypress.session.clearAllSavedSessions()
        cy.logf("Logging in as a superuser", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaUI(users.superuser.email, users.superuser.password)
        })

        cy.logf("Creating new flavors in the regular user's project", Cypress.currentTest)
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('[data-cy="settings"]').should('be.visible').click()
        cy.get('.list-group').find('a').should('be.visible').contains('Flavors').click()
        cy.get('input[name="flavor_name"]').type(new_flavor_name)
        cy.get('input[name="cpu_req"]').clear().type("100m")
        cy.get('input[name="cpu_lim"]').clear().type("4000m")
        cy.get('input[name="mem_req"]').clear().type("2Gi")
        cy.get('input[name="mem_lim"]').clear().type("8Gi")
        cy.get('button').should('be.visible').contains("Create flavor").click()

        cy.get('.list-group').should('be.visible').find('a').contains('Flavors').click()
        cy.get('input[name="flavor_name"]').type(new_flavor_name_unused)
        cy.get('input[name="cpu_req"]').clear().type("100m")
        cy.get('input[name="cpu_lim"]').clear().type("4000m")
        cy.get('input[name="mem_req"]').clear().type("2Gi")
        cy.get('input[name="mem_lim"]').clear().type("8Gi")
        cy.get('button').should('be.visible').contains("Create flavor").click()

        cy.logf("Creating new Jupyter Lab environments in the regular user's project", Cypress.currentTest)
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('[data-cy="settings"]').should('be.visible').click()
        cy.get('.list-group').should('be.visible').find('a').contains('Environments').click()
        cy.get('input[name="environment_name"]').type(new_environment_name)
        cy.get('input[name="environment_repository"]').clear().type("docker.io")
        cy.get('input[name="environment_image"]').clear().type("jupyter/minimal-notebook:latest")
        cy.get('#environment_app').select('Jupyter Lab')
        cy.get('button').should('be.visible').contains("Create environment").click()

        cy.get('.list-group').should('be.visible').find('a').contains('Environments').click()
        cy.get('input[name="environment_name"]').type(new_environment_name_unused)
        cy.get('input[name="environment_repository"]').clear().type("docker.io")
        cy.get('input[name="environment_image"]').clear().type("jupyter/minimal-notebook:latest")
        cy.get('#environment_app').select('Jupyter Lab')
        cy.get('button').should('be.visible').contains("Create environment").click()

        const createResources = Cypress.env('create_resources');

        if (createResources === true) {

            Cypress.session.clearAllSavedSessions()
            cy.logf("Logging back in as a regular user and using the new flavor and environment", Cypress.currentTest)
            cy.fixture('users.json').then(function (data) {
                users = data
                cy.loginViaUI(users.superuser_testuser.email, users.superuser_testuser.password)
            })

            cy.logf("Checking the flavour functionality", Cypress.currentTest)

            const app_type_flavor = "Dash App"
            const app_name_flavor = "e2e-dash-example"
            const app_description = "e2e-dash-description"
            const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
            const image_port = "8000"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type_flavor + '")').should('be.visible').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_flavor)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            cy.get('#id_flavor').select('2 vCPU, 4 GB RAM')
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()

            // Check that the app is visible and verify the app status
            verifyAppStatus(app_name_flavor, "Creating", "project", "Creating")

            // cy.get('tr:contains("' + app_name_flavor + '")', {timeout: longCmdTimeoutMs}).find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Running')

            cy.logf("Changing the flavor setting", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_flavor + '")').should('be.visible').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_flavor + '")').should('be.visible').find('a').contains('Settings').click()
            cy.get('#id_flavor').find(':selected').should('contain', '2 vCPU, 4 GB RAM')
            cy.get('#id_flavor').select(new_flavor_name)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()

            // Check that the app is visible and verify the app status
            verifyAppStatus(app_name_flavor, "", "project", "Changing")

            // cy.get('tr:contains("' + app_name_flavor + '")', {timeout: longCmdTimeoutMs}).find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Running')

            cy.logf("Checking that the new flavor setting was saved in the database", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_flavor + '")').should('be.visible').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_flavor + '")').should('be.visible').find('a').contains('Settings').click()
            cy.get('#id_flavor').find(':selected').should('contain', new_flavor_name)

            cy.logf("Checking the Jupyter Lab environment functionality", Cypress.currentTest)

            const app_type_env = "Jupyter Lab"
            const app_name_env = "e2e-jupyter-lab-env-test"

            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type_env + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').should('be.visible').type(app_name_env)
            cy.logf("Checking that Jupyter Lab has the four different environments", Cypress.currentTest)
            // Check the environment dropdown options
            cy.get('#id_environment').as('envSelect');
            [
                'Jupyter Lab Minimal (Default)',
                'Jupyter Lab Data Science',
                'Jupyter Lab PyTorch',
                'Jupyter Lab Tensorflow'
            ].forEach((name) => {
            cy.get('@envSelect').contains('option', name);
            });
            cy.get('#id_environment').select('Jupyter Lab Minimal (Default)')
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()

            // Check that the app is visible and verify the app status
            verifyAppStatus(app_name_env, "", "", "Creating")

            // cy.get('tr:contains("' + app_name_env + '")', {timeout: longCmdTimeoutMs}).find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Running')

            cy.logf("Changing the environment setting", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_env + '")').should('be.visible').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_env + '")').should('be.visible').find('a').contains('Settings').click()
            cy.get('#id_environment').find(':selected').should('contain', 'Jupyter Lab Minimal (Default)')
            cy.get('#id_environment').select(new_environment_name)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()

            // Check that the app is visible and verify the app status
            verifyAppStatus(app_name_env, "", "", "Changing")

            // cy.get('tr:contains("' + app_name_env + '")', {timeout: longCmdTimeoutMs}).find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Running')

            cy.logf("Checking that the new environment setting was saved in the database", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_env + '")').should('be.visible').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_env + '")').should('be.visible').find('a').contains('Settings').click()
            cy.get('#id_environment').find(':selected').should('contain', new_environment_name)

            cy.logf("Checking that admin cannot delete flavor or environment currently in use", Cypress.currentTest)
            cy.logf("Logging in as a superuser", Cypress.currentTest)
            // I do this logout and login manually (rather than using Cypress sessions) because Cypress
            // refused to do one more session for this user here for some reason
            cy.get('button.btn-profile').should('be.visible').contains("Profile").click()
            cy.get('li.btn-group').should('be.visible').find('button').contains("Sign out").click()
            cy.get("title").should("have.text", "Logout | SciLifeLab Serve (beta)")
            cy.fixture('users.json').then(function (data) {
                users = data
                cy.visit('/accounts/login/')
                cy.get('input[name=username]').type(users.superuser.email)
                cy.get('input[name=password]').type(`${users.superuser.password}{enter}`, { log: false })
                cy.url().should('include', '/projects')
                cy.get('h3').should('contain', 'My projects')
            })

            cy.logf("Trying to delete a flavor that was used", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('[data-cy="settings"]').should('be.visible').click()
            cy.logf("Deleting a flavor that was used", Cypress.currentTest)
            cy.get('.list-group').should('be.visible').find('a').contains('Flavors').click()
            cy.get('#flavor_pk').select(new_flavor_name)
            cy.get('button').should('be.visible').contains("Delete flavor").click()
            cy.get('div.alert-danger').contains('Flavor cannot be deleted').should('exist')

            cy.logf("Deleting a flavor that was not used", Cypress.currentTest)
            cy.logf("Trying flavor deletion", Cypress.currentTest)
            cy.get('.list-group').should('be.visible').find('a').contains('Flavors').click()
            cy.get('#flavor_pk').select(new_flavor_name_unused)
            cy.get('button').should('be.visible').contains("Delete flavor").click()
            cy.get('.list-group').should('be.visible').find('a').contains('Flavors').click()
            cy.get('#flavor_pk').contains(new_flavor_name_unused).should("not.exist")

            cy.logf("Trying to delete an environment that was used", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('[data-cy="settings"]').should('be.visible').click()
            cy.logf("Deleting a flavor that was used", Cypress.currentTest)
            cy.get('.list-group').should('be.visible').find('a').contains('Environments').click()
            cy.get('#environment_pk').select(new_environment_name)
            cy.get('button').should('be.visible').contains("Delete environment").click()
            cy.get('div.alert-danger').contains('Environment cannot be deleted').should('exist')

            cy.logf("Deleting an environment that was not used", Cypress.currentTest)
            cy.get('.list-group').should('be.visible').find('a').contains('Environments').click()
            cy.get('#environment_pk').select(new_environment_name_unused)
            cy.get('button').should('be.visible').contains("Delete environment").click()
            cy.get('.list-group').should('be.visible').find('a').contains('Environments').click()
            cy.get('#environment_pk').contains(new_environment_name_unused).should("not.exist")

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
        }

        cy.logf("Deleting the created project", Cypress.currentTest)
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
        .then((href) => {
            cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                cy.get('div#modalConfirmDeleteFooter').should('be.visible').find('button').contains('Delete').click()
                cy.contains(project_name).should('not.exist') // confirm the project has been deleted
           })
        })
    })

    it("can bypass N projects limit", () => {
        // Names of projects to create
        const project_name = "e2e-superuser-proj-limits-test"

        cy.logf("Create 10 projects (current limit for regular users) with the same name (currently not possible for regular users to use the same name)", Cypress.currentTest)
        Cypress._.times(10, () => {
            // better to write this out rather than use the createBlankProject command because then we can do a 5000 ms pause only once
            cy.visit("/projects/")
            cy.get("a").should('be.visible').contains('New project').click()
            cy.get("a").should('be.visible').contains('Create').first().click()
            cy.get('input[name=name]').type(project_name)
            cy.get("input[name=save]").should('be.visible').contains('Create project').click()
            cy.wait(5000)
        });
        cy.wait(15000) // sometimes it takes a while to create a project but just waiting once at the end should be enough

        cy.logf("Check that it is still possible to click the button to create a new project", Cypress.currentTest)
        cy.visit("/projects/")
        cy.get("a").should('be.visible').contains('New project').should('exist')

        cy.logf("Create one more project to check it is possible to bypass the limit", Cypress.currentTest)
        cy.createBlankProject(project_name)
        cy.visit("/projects/")
        cy.get('h5:contains("' + project_name + '")').its('length').should('eq', 11) // check that the superuser now bypassed the limit for regular users

        cy.logf("Now delete all created projects", Cypress.currentTest)
        Cypress._.times(11, () => {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').should('be.visible').find('button').contains('Delete').click()
               })
            })
        });
    })

    it("can bypass N apps limit", () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test-apps-limit"
        const app_name = "e2e-create-jl"

         cy.logf("Creating a blank project", Cypress.currentTest)
         cy.createBlankProject(project_name)
            .then(() => {
                cy.logf("Create 3 jupyter lab instances (current limit)", Cypress.currentTest)
                Cypress._.times(3, () => {
                        cy.get('div.card-body:contains("Jupyter Lab")').siblings('.card-footer').find('a:contains("Create")').click()
                        cy.get('#id_name').type(app_name)
                        cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
                });
                cy.logf("Check that the button to create another one still works", Cypress.currentTest)
                cy.get('div.card-body:contains("Jupyter Lab")').siblings('.card-footer').find('a:contains("Create")').should('have.attr', 'href')
                cy.logf("Check that it is possible to create another one and therefore bypass the limit", Cypress.currentTest)
                cy.get('div.card-body:contains("Jupyter Lab")').siblings('.card-footer').find('a:contains("Create")').click()
                cy.get('#id_name').type(app_name)
                cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
                cy.get('tr:contains("' + app_name + '")').its('length').should('eq', 4) // we now have an extra app
                })

         cy.logf("Deleting the created project", Cypress.currentTest)
         cy.visit("/projects/")
         cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
         .then((href) => {
             cy.get('div#modalConfirmDelete').should('have.css', 'display', 'block')
             cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                 cy.get('div#modalConfirmDeleteFooter').should('be.visible').find('button').contains('Delete').click()
                 cy.contains(project_name).should('not.exist') // confirm the project has been deleted
            })
         })


    })

    it("can add pages to user docs", () => {

        const root_article_name = "user-documentation"
        const root_article_content = "user-documentation-homepage"
        const regular_article_name ="regular-article"
        const regular_article_slug ="regular-article"
        const regular_article_content = "regular-article-content"

        cy.logf("Creating the root article", Cypress.currentTest)
        cy.visit("/docs/")
        cy.get('h1').should('contain', 'Congratulations') // check that django-wiki was correctly installed
        cy.get('#id_title').clear().type(root_article_name)
        cy.get('#id_content').clear().type(root_article_content)
        cy.get('button[name="save_changes"]').should('be.visible').click()
        cy.logf("Checking that the root article was successfully created", Cypress.currentTest)
        cy.get('h1#article-title').contains(root_article_name)
        cy.get('div.wiki-article').contains(root_article_content)

        cy.logf("Adding a regular article", Cypress.currentTest)
        cy.get(".btn-group").get(".btn").should('be.visible').contains("Add a new article").click()
        cy.get(".btn-group").get("a.dropdown-item").should('be.visible').contains("New article below").click()
        cy.url().should("include", "/docs/_create/")
        cy.get('#id_title').clear().type(regular_article_name)
        cy.get('#id_content').clear().type(regular_article_content)
        cy.get('button[name="save_changes"]').should('be.visible').click()
        cy.logf("Checking that the regular article was successfully created", Cypress.currentTest)
        cy.url().should("include", regular_article_slug)
        cy.get('h1#article-title').contains(regular_article_name)
        cy.get('div.wiki-article').contains(regular_article_content)
    })

    after(() => {

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Cleaning up test data via Django endpoint");
            cy.cleanupAllTestProjects(TEST_SUPER_USER_DATA);
            cy.cleanupAllTestProjects(TEST_USER_DATA);
            cy.cleanupTestUser(TEST_SUPER_USER_DATA);
            cy.cleanupTestUser(TEST_USER_DATA);
        }

        cy.logf("End after() hook", Cypress.currentTest)
    })

})
