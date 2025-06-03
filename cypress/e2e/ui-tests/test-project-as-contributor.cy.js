describe("Test project contributor user functionality", () => {

    // Tests performed as an authenticated user that creates and deletes objects.

    // The default command timeout should not be so long
    // Instead use longer timeouts on specific commands where deemed necessary and valid
    const defaultCmdTimeoutMs = 10000
    // The longer timeout is often used when waiting for k8s operations to complete
    const longCmdTimeoutMs = 180000

    // user: e2e_tests_contributor_tester
    let users

    let TEST_CONTRIBUTOR_USER_DATA

    const TEST_CONTRIBUTOR_PROJECT_DATA = {
        project_name: "e2e-delete-proj-test",
        project_description: "e2e-delete-proj-test-desc",
      };

    let TEST_COLLABORATOR_USER_DATA

    const TEST_COLLABORATOR_PROJECT_DATA = {
        project_name: "e2e-collaborator-proj-test",
        project_description: "e2e-collaborator-proj-test-desc",
      };

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest)

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Populating test data via Django endpoint");
            cy.fixture('users.json').then(function (data) {
                TEST_CONTRIBUTOR_USER_DATA = data.contributor;
                cy.populateTestUser(TEST_CONTRIBUTOR_USER_DATA);
                cy.populateTestProject(TEST_CONTRIBUTOR_USER_DATA, TEST_CONTRIBUTOR_PROJECT_DATA);
                TEST_COLLABORATOR_USER_DATA = data.contributor_collaborator;
                cy.populateTestUser(TEST_COLLABORATOR_USER_DATA);
                cy.populateTestProject(TEST_COLLABORATOR_USER_DATA, TEST_COLLABORATOR_PROJECT_DATA);
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
            cy.logf("Running seed_contributor.py", Cypress.currentTest)
            cy.exec("./cypress/e2e/db-seed-contributor.sh")
        }

        cy.logf("End before() hook", Cypress.currentTest)
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)

        // email in fixture must match email in db-reset.sh
        cy.logf("Logging in as contributor user", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.contributor.email, users.contributor.password)
        })

        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("can create a new project with default template, open settings, change description, delete from settings", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // Names of objects to create
        const project_name = "e2e-create-default-proj-test"
        const project_name_2 = "An alternative project name created by an e2e test."
        const project_title_name = project_name + " | SciLifeLab Serve (beta)"
        const project_description = "A test project created by an e2e test."
        const project_description_2 = "An alternative project description created by an e2e test."

        cy.visit("/projects/")
        cy.get("title").should("have.text", "My projects | SciLifeLab Serve (beta)")

        cy.logf("Create a new project", Cypress.currentTest)
        // Click button for UI to create a new project
        cy.get("a").contains('New project').click()
        cy.url().should("include", "projects/templates")
        cy.get('h3').should('contain', 'New project')

        // Next click button to create a new blank project
        cy.get("a").contains('Create').first().click()
        cy.url().should("include", "projects/create/?template=")
        cy.get('h3').should('contain', 'New project')

        // Fill in the options for creating a new blank project
        cy.get('input[name=name]').type(project_name)
        cy.get('textarea[name=description]').type(project_description)
        cy.get("input[name=save]").contains('Create project').click()
        cy.wait(5000) // sometimes it takes a while to create a project

        cy.get("title").should("have.text", project_title_name)
        cy.get('h3').should('contain', project_name)
        cy.get('.card-text').should('contain', project_description)

        cy.logf("Check that the correct deployment options are available", Cypress.currentTest)
        cy.get('.card-header').find('h5').should('contain', 'Develop')
        cy.get('.card-header').find('h5').should('contain', 'Serve')
        cy.get('.card-header').find('h5').should('not.contain', 'Models')
        cy.get('.card-header').find('h5').should('not.contain', 'Additional options [admins only]')

        cy.logf("Check that project settings are available", Cypress.currentTest)
        cy.get('[data-cy="settings"]').click()
        cy.url().should("include", "settings")
        cy.get('h3').should('contain', 'Project settings')

        cy.logf("Check that the correct project settings are visible (i.e. no extra settings)", Cypress.currentTest)
        cy.get('.list-group').find('a').should('contain', 'Access')
        cy.get('.list-group').find('a').should('not.contain', 'S3 storage')
        cy.get('.list-group').find('a').should('not.contain', 'MLFlow')
        cy.get('.list-group').find('a').should('not.contain', 'Flavors')
        cy.get('.list-group').find('a').should('not.contain', 'Environments')

        cy.logf("Change project description", Cypress.currentTest)
        cy.get('textarea[name=description]').clear().type(project_description_2)
        cy.get('button').contains('Save').click()
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('.card-text').should('contain', project_description_2)

        cy.logf("Change project name", Cypress.currentTest)
        cy.get('[data-cy="settings"]').click()
        cy.get('input[name=name]').clear().type(project_name_2)
        cy.get('button').contains('Save').click()
        cy.visit("/projects/")
        cy.contains('.card-title', project_name_2).should('contain', project_name_2)

        cy.logf("Check that creating another project with same existing project name will create an error", Cypress.currentTest)
        cy.visit("/projects/")
        cy.get("a").contains('New project').click()
        cy.get("a").contains('Create').first().click()
        cy.get('input[name=name]').type(project_name_2) // same name used before
        cy.get('textarea[name=description]').type(project_description)
        cy.get("input[name=save]").contains('Create project').click() // should generate an error
        // Check that the error message is displayed
        cy.get('#flash-msg')
            .should('be.visible')
            .and('have.class', 'alert-danger')
            .and('contain.text', `Project cannot be created because a project with name '${project_name_2}' already exists.`);
        cy.logf("Error is successfully generated when trying to create a new project with the same existing project name", Cypress.currentTest)

        // go back to the previously created project
        cy.visit("/projects/")
        cy.contains('.card-title', project_name_2).parents('.card-body').siblings('.card-footer').find('a.btn').contains('Open').click()

        cy.logf("Delete the project from the settings menu", Cypress.currentTest)
        cy.get('[data-cy="settings"]').click()
        cy.get('a').contains("Delete").click()
        .then((href) => {
            cy.get('div#delete').should('have.css', 'display', 'block')
            cy.get('#id_delete_button').parent().parent().find('button').contains('Delete').click()
            .then((href) => {
                cy.get('div#deleteModal').should('have.css', 'display', 'block')
                cy.get('div#deleteModal').find('button').contains('Confirm').click()
            })
        cy.contains(project_name_2).should('not.exist')

        })
    })

    it("can delete a project from projects overview", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // Names of objects to create
        const project_name = "e2e-delete-proj-test"

        cy.visit("/projects/")

        // Verify that the test project has been created
        cy.get('h5.card-title').should('contain', project_name)

        cy.get('div#modalConfirmDelete').should('have.css', 'display', 'none')

        // Next click button to delete the project
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get('div#modalConfirmDelete').should('have.css', 'display', 'block')

                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.logf($elem.text(), Cypress.currentTest)

                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()

                    // Assert that the project has been deleted
                    cy.contains(project_name).should('not.exist')
               })
            })
    })

    it("limit on number of apps per project is enforced", () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test-1"

        // Create a project
        cy.visit("/projects/")
        cy.get("a").contains('New project').click()
        cy.get("a").contains('Create').first().click()
        cy.get('input[name=name]').type(project_name)
        cy.get("input[name=save]").contains('Create project').click()
        cy.wait(10000) // sometimes it takes a while to create a project
            .then((href) => {
                cy.logf(href, Cypress.currentTest)
                // Check that the app limits work using Jupyter Lab as example
                // step 1. create 3 jupyter lab instances (current limit)
                Cypress._.times(3, () => {
                        cy.get('div.card-body:contains("Jupyter Lab")').siblings('.card-footer').find('a:contains("Create")').click()
                        cy.get('#id_name').type("e2e-create-jl")
                        cy.get('#submit-id-submit').contains('Submit').click()
                  });
                // step 2. check that the button to create another one does not work
                cy.get('div.card-body:contains("Jupyter Lab")').siblings('.card-footer').find('button:contains("Create")').should('not.have.attr', 'href')
                // step 3. check that it is not possible to create another one using direct url
                let projectURL
                    cy.url().then(url => {
                        projectURL = url
                    });
                cy.then(() =>
                    cy.request({url: projectURL + "apps/create/jupyter-lab?from=overview", failOnStatusCode: false}).its('status').should('equal', 403)
                    )
                })

        // Delete the created project
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
               })
            })
    })

    it("limit on number of projects per user is enforced", () => {
        // Names of projects to create
        const project_name = "e2e-create-proj-test-2"

        // Create 10 projects (current limit)
        Cypress._.times(10, (i) => {
            cy.visit("/projects/")
            cy.get("a").contains('New project').click()
            cy.get("a").contains('Create').first().click()
            cy.get('input[name=name]').type(`${project_name}-${i + 1}`);
            cy.get("input[name=save]").contains('Create project').click()
            cy.wait(5000)
        });
        cy.wait(15000) // sometimes it takes a while to create a project but just waiting once at the end should be enough

        // Now check that it is not possible to create another project
        // not possible to click the button to create a new project
        cy.visit("/projects/")
        cy.get("button").contains('New project').should('not.have.attr', 'href')
        // if accessing directly with the url, the request is not accepted
        cy.request({url: "/projects/create/", failOnStatusCode: false}).its('status').should('equal', 403)
        cy.request({url: "/projects/templates/", failOnStatusCode: false}).its('status').should('equal', 403)

        // Now delete all created projects
        Cypress._.times(10, () => {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
               })
            })
        });
    })

    it("cannot see a project of another user without appropriate access", () => {
        const project_name = "e2e-collaborator-proj-test" // from seed_contributor.py

        // First we need to get a URL of the second user's project
        // log in as second user
        cy.logf("Now logging in as the second user", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaUI(users.contributor_collaborator.email, users.contributor_collaborator.password)
        })

        // get the second user's project's URL
        cy.logf("Checking the second user's project URL", Cypress.currentTest)
        cy.visit('/projects/')
        cy.get('h5.card-title').should('contain', project_name) // check access to project
        cy.get('a.btn').contains('Open').click()
        .then((href) => {
            cy.logf(href, Cypress.currentTest)
            let projectURL
                cy.url().then(url => {
                    projectURL = url
                });
            // Now we can check if the contributor user has access to this project
            // log back in as contributor user
            cy.logf("Now logging back in as contributor user", Cypress.currentTest)
            cy.fixture('users.json').then(function (data) {
                users = data
                cy.loginViaApi(users.contributor.email, users.contributor.password)
            })
            cy.logf("Checking that can't see the project in the list of projects", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).should('not.exist') // cannot see the project
            cy.logf("Checking that can't open the project using direct URL", Cypress.currentTest)
            cy.then(() =>
                cy.request({url: projectURL, failOnStatusCode: false}).its('status').should('equal', 403) // cannot open the project using a direct link
                )
            // Finally, unauthenticated user
            cy.logf("Logging out the contributor user and testing as an unauthenticated user", Cypress.currentTest)
            cy.clearCookies();
            cy.clearLocalStorage();
            Cypress.session.clearAllSavedSessions()
            cy.then(() =>
            cy.request({url: projectURL, failOnStatusCode: false}).its('status').should('equal', 403) // cannot open the project using a direct link
            )
            })
    })

    it("can give and revoke access to a project to another user", () => {
        // Names of projects and apps to create
        const project_name_access = "e2e-access-proj-test"
        const private_app_name = "e2e-private-app-test"
        const project_app_name = "e2e-project-app-test"
        const app_type = "Jupyter Lab"

        // Create a project
        cy.logf("Now creating a project", Cypress.currentTest)
        cy.visit("/projects/")
        // Click button for UI to create a new project
        cy.get("a").contains('New project').click()
        // Next click button to create a new blank project
        cy.get("a").contains('Create').first().click()
        // Fill in the options for creating a new blank project
        cy.get('input[name=name]').type(project_name_access)
        cy.get('textarea[name=description]').type("A test project created by an e2e test.")
        cy.get("input[name=save]").contains('Create project').click()
        cy.wait(5000) // sometimes it takes a while to create a project

        // Create private app
        cy.logf("Now creating a private app", Cypress.currentTest)
        cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
        cy.get('#id_name').type(private_app_name)
        cy.get('#id_access').select('Private')
        cy.get('#submit-id-submit').contains('Submit').click() // create app
        cy.get('tr:contains("' + private_app_name + '")').find('span').should('contain', 'private') // check that the app got greated

        // Create project app
        cy.logf("Now creating a project app", Cypress.currentTest)
        cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
        cy.get('#id_name').type(project_app_name)
        cy.get('#id_access').select('Project')
        cy.get('#submit-id-submit').contains('Submit').click() // create app
        cy.get('tr:contains("' + project_app_name + '")').find('span').should('contain', 'project') // check that the app got greated

        // Give access to this project to a collaborator user
        cy.logf("Now giving access to another user", Cypress.currentTest)
        // Go to project settings
        cy.get('[data-cy="settings"]').click()
        cy.get('a[href="#access"]').click()
        // Give access to contributor
        cy.fixture('users.json').then(function (data) {
            cy.get('input[name=selected_user]').type(users.contributor_collaborator.email)
        })
        cy.get('button').contains('Grant access').click()
        cy.fixture('users.json').then(function (data) {
            cy.get('tr.user-with-access').should('contain', users.contributor_collaborator.email)
        })

        // Log out step is not needed because cypress sessions take care of that

        // Log in as contributor's collaborator user
        cy.logf("Now logging in as contributor's collaborator user", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaUI(users.contributor_collaborator.email, users.contributor_collaborator.password)
        })

        // Check that the contributor's collaborator user has correct access
        cy.logf("Now checking access to project and apps", Cypress.currentTest)
        cy.visit('/projects/')
        cy.get('h5.card-title').should('contain', project_name_access) // check access to project
        cy.contains('.card-title', project_name_access).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('tr:contains("' + private_app_name + '")').should('not.exist') // private app not visible
        // to be added: go to URL and check that it does not open
        cy.get('tr:contains("' + project_app_name + '")').should('exist') // project app visible
        // to be added: go to URL and check that it opens successfully

        // Log back in as contributor user
        cy.logf("Now logging back in as contributor user", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaApi(users.contributor.email, users.contributor.password)
        })

        // Remove access to the project
        cy.logf("Now removing access from contributor's collaborator user", Cypress.currentTest)
        cy.visit('/projects/')
        cy.contains('.card-title', project_name_access).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('[data-cy="settings"]').click()
        cy.get('a[href="#access"]').click()
        cy.get('tr.user-with-access').find('button.btn-close').click()
        .then((href) => {
            cy.get('button.btn-danger').contains('Revoke').click()
        })

        // Log in as contributor's collaborator user
        cy.logf("Now again logging in as contributor's collaborator user", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaUI(users.contributor_collaborator.email, users.contributor_collaborator.password)
        })

        // Check that the contributor's collaborator user no longer has access to the project
        cy.logf("Now checking that contributor's collaborator user no longer has access", Cypress.currentTest)
        cy.visit('/projects/')
        cy.contains('.card-title', project_name_access).should('not.exist') // check visibility of project
        // to-do: save the url of the project in a previous step and check if possible to open that with a direct link

        // Log back in as contributor user
        cy.logf("Now logging back in as contributor user", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaApi(users.contributor.email, users.contributor.password)
        })

        // Delete the created project
        cy.logf("Now deleting the created project", Cypress.currentTest)
        cy.visit("/projects/")
        cy.contains('.card-title', project_name_access).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
                    cy.contains(project_name_access).should('not.exist') // confirm the project has been deleted
               })
            })
    })

    it("can create a file management instance", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
        const project_name = "e2e-create-proj-test-3"

        cy.logf("Creating a blank project", Cypress.currentTest)
        cy.createBlankProject(project_name)

        cy.logf("Activating file managing tools", Cypress.currentTest)
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('div.card-body:contains("File Manager")').siblings('.card-footer').find('a:contains("Create")').click()
        cy.get('#submit-id-submit').should('be.visible').click()

        cy.get('tr:contains("File Manager")').find('[data-cy="appstatus"]').should('have.attr', 'data-app-action', 'Creating')
    })

    after(() => {

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Cleaning up test data via Django endpoint");
            cy.cleanupAllTestProjects(TEST_CONTRIBUTOR_USER_DATA);
            cy.cleanupAllTestProjects(TEST_COLLABORATOR_USER_DATA);
            cy.cleanupTestUser(TEST_CONTRIBUTOR_USER_DATA);
            cy.cleanupTestUser(TEST_COLLABORATOR_USER_DATA);
        }

        cy.logf("End after() hook", Cypress.currentTest)
    })
})
