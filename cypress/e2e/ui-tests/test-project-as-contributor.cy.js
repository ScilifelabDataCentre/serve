describe("Test project contributor user functionality", () => {

    // Tests performed as an authenticated user that
    // creates and deletes objects.
    // user: e2e_tests_contributor_tester

    let users

    before(() => {
        // do db reset if needed
        if (Cypress.env('do_reset_db') === true) {
            cy.log("Resetting db state. Running db-reset.sh");
            cy.exec("./cypress/e2e/db-reset.sh");
            cy.wait(Cypress.env('wait_db_reset'));
        }
        else {
            cy.log("Skipping resetting the db state.");
        }
        // seed the db with a user
        cy.visit("/")
        cy.log("Running seed_contributor.py")
        cy.exec("./cypress/e2e/db-seed-contributor.sh")
    })

    beforeEach(() => {
        // email in fixture must match email in db-reset.sh
        cy.log("Logging in as contributor user")
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.contributor.email, users.contributor.password)
        })
    })


    it("can run the test setup", () => {
    })

    it("can create a new project with default template, open settings, change description, delete from settings", { defaultCommandTimeout: 100000 }, () => {

        // Names of objects to create
        const project_name = "e2e-create-default-proj-test"
        const project_title_name = project_name + " | SciLifeLab Serve (beta)"
        const project_description = "A test project created by an e2e test."
        const project_description_2 = "An alternative project description created by an e2e test."

        cy.visit("/projects/")
        cy.get("title").should("have.text", "My projects | SciLifeLab Serve (beta)")

        // Click button for UI to create a new project
        cy.get("a").contains('New project').click()
        cy.url().should("include", "projects/templates")
        cy.get('h3').should('contain', 'New project')

        // Next click button to create a new blank project
        cy.get("a").contains('Create').first().click()
        cy.url().should("include", "projects/create?template=")
        cy.get('h3').should('contain', 'New project')

        // Fill in the options for creating a new blank project
        cy.get('input[name=name]').type(project_name)
        cy.get('textarea[name=description]').type(project_description)
        cy.get("input[name=save]").contains('Create project').click()
        cy.wait(5000) // sometimes it takes a while to create a project

        cy.get("title").should("have.text", project_title_name)
        cy.get('h3').should('contain', project_name)
        cy.get('.card-text').should('contain', project_description)

        // Check that the correct deployment options are available
        cy.get('.card-header').find('h5').should('contain', 'Develop')
        cy.get('.card-header').find('h5').should('contain', 'Serve')
        cy.get('.card-header').find('h5').should('not.contain', 'Models')
        cy.get('.card-header').find('h5').should('not.contain', 'Additional options [admins only]')

        // Check that project settings are available
        cy.get('[data-cy="settings"]').click()
        cy.url().should("include", "settings")
        cy.get('h3').should('contain', 'Project settings')

        // Check that the correct project settings are visible (i.e. no extra settings)
        cy.get('.list-group').find('a').should('contain', 'Access')
        cy.get('.list-group').find('a').should('not.contain', 'S3 storage')
        cy.get('.list-group').find('a').should('not.contain', 'MLFlow')
        cy.get('.list-group').find('a').should('not.contain', 'Flavors')
        cy.get('.list-group').find('a').should('not.contain', 'Environments')

        // Change project description - THIS DOES NOT WORK RIGHT NOW BECAUSE OF A BUG, TO BE ADDED/ACTIVATED LATER
        //cy.get('textarea[name=description]').clear().type(project_description_2)
        //cy.get('button').contains('Save').click()
        //cy.visit("/projects/")
        //cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        //cy.get('.card-text').should('contain', project_description_2)

        // Delete the project from the settings menu
        //cy.get('[data-cy="settings"]').click()
        cy.get('a').contains("Delete").click()
        .then((href) => {
            cy.get('div#delete').should('have.css', 'display', 'block')
            cy.get('#id_delete_button').parent().parent().find('button').contains('Delete').click()
            .then((href) => {
                cy.get('div#deleteModal').should('have.css', 'display', 'block')
                cy.get('div#deleteModal').find('button').contains('Confirm').click()
            })
        cy.contains(project_name).should('not.exist')

        })
    })

    // This test cannot run properly in GitHub workflows because there is an issue with minio creation there. Therefore, it should be run locally to make sure things work. For GitHub, skipping it.

    // TODO: When models are launched, make sure that this test is activated
    it.skip("can create a new project with ML serving template, open settings, delete from settings", { defaultCommandTimeout: 100000 }, () => {

        // Names of objects to create
        const project_name = "e2e-create-ml-proj-test"
        const project_title_name = project_name + " | SciLifeLab Serve (beta)"

        cy.visit("/projects/")
        cy.get("title").should("have.text", "My projects | SciLifeLab Serve (beta)")

        // Click button for UI to create a new project
        cy.get("a").contains('New project').click()
        cy.url().should("include", "projects/templates")
        cy.get('h3').should('contain', 'New project')

        // Next click button to create a new blank project
        cy.get(".card-footer").last().contains("Create").click()
        cy.url().should("include", "projects/create?template=")
        cy.get('h3').should('contain', 'New project')

        // Fill in the options for creating a new blank project
        cy.get('input[name=name]').type(project_name)
        cy.get('textarea[name=description]').type("A test project created by an e2e test.")
        cy.get("input[name=save]").contains('Create project').click()
        cy.wait(5000) // sometimes it takes a while to create a project
            .then((href) => {
                cy.log(href)
                cy.reload()
                cy.get("title").should("have.text", project_title_name)
                cy.get('h3').should('contain', project_name)

                // Check that the correct deployment options are available
                cy.get('.card-header').find('h5').should('contain', 'Develop')
                cy.get('.card-header').find('h5').should('contain', 'Serve')
                cy.get('.card-header').find('h5').should('contain', 'Models')
                cy.get('.card-header').find('h5').should('not.contain', 'Additional options [admins only]')

                // Section Models - Machine Learning Models
                // Navigate to the create models view and cancel back again
                cy.get("div#models").first("h5").should("contain", "Machine Learning Models")
                cy.get("div#models").find("a.btn").click()
                    .then((href) => {
                        cy.url().should("include", "models/create")
                        cy.get('h3').should("contain", "Create Model Object")
                        cy.get("button").contains("Cancel").click()
                            .then((href) => {
                                cy.get('h3').should("contain", project_name)
                        })
                    })

                // Check that project settings are available
                cy.get('[data-cy="settings"]').click()
                cy.url().should("include", "settings")
                cy.get('h3').should('contain', 'Project settings')

                // Check that the correct project settings are visible (i.e. no extra settings)
                cy.get('.list-group').find('a').should('contain', 'Access')
                cy.get('.list-group').find('a').should('not.contain', 'S3 storage')
                cy.get('.list-group').find('a').should('not.contain', 'MLFlow')
                cy.get('.list-group').find('a').should('not.contain', 'Flavors')
                cy.get('.list-group').find('a').should('not.contain', 'Environments')

                // Delete the project from the settings menu
                cy.get('a').contains("Delete").click()
                .then((href) => {
                    cy.get('div#delete').should('have.css', 'display', 'block')
                    cy.get('#id_delete_button').parent().parent().find('button').contains('Delete').click()
                    .then((href) => {
                        cy.get('div#deleteModal').should('have.css', 'display', 'block')
                        cy.get('div#deleteModal').find('button').contains('Confirm').click()
                    })
                    cy.contains(project_name).should('not.exist')

                   })
            })
    })

    it.skip("can create a new mlflow project", () => {
    })

    it("can delete a project from projects overview", { defaultCommandTimeout: 100000 }, () => {

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
                    cy.log($elem.text())

                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()

                    // Assert that the project has been deleted
                    cy.contains(project_name).should('not.exist')
               })
            })
    })

    it("limit on number of apps per project is enforced", () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test"

        // Create a project
        cy.visit("/projects/")
        cy.get("a").contains('New project').click()
        cy.get("a").contains('Create').first().click()
        cy.get('input[name=name]').type(project_name)
        cy.get("input[name=save]").contains('Create project').click()
        cy.wait(5000) // sometimes it takes a while to create a project
            .then((href) => {
                cy.log(href)
                // Check that the app limits work using Jupyter Lab as example
                // step 1. create 3 jupyter lab instances (current limit)
                Cypress._.times(3, () => {
                        cy.get('[data-cy="create-app-card"]').contains('Jupyter Lab').parent().siblings().find('.btn').click()
                        cy.get('input[name=app_name]').type("e2e-create-jl")
                        cy.get('.btn-primary').contains('Create').click()
                  });
                // step 2. check that the button to create another one does not work
                cy.get('[data-cy="create-app-card"]').contains('Jupyter Lab').parent().siblings().find('.btn').should('not.have.attr', 'href')
                // step 3. check that it is not possible to create another one using direct url
                let projectURL
                    cy.url().then(url => {
                        projectURL = url
                    });
                cy.then(() =>
                    cy.request({url: projectURL + "/apps/create/jupyter-lab?from=overview", failOnStatusCode: false}).its('status').should('equal', 403)
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
        const project_name = "e2e-create-proj-test"

        // Create 5 projects (current limit)
        Cypress._.times(5, () => {
            cy.visit("/projects/")
            cy.get("a").contains('New project').click()
            cy.get("a").contains('Create').first().click()
            cy.get('input[name=name]').type(project_name)
            cy.get("input[name=save]").contains('Create project').click()
        });
        cy.wait(5000) // sometimes it takes a while to create a project but just waiting once at the end should be enough

        // Now check that it is not possible to create another project
        // not possible to click the button to create a new project
        cy.visit("/projects/")
        cy.get("button").contains('New project').should('not.have.attr', 'href')
        // if accessing directly with the url, the request is not accepted
        cy.request({url: "/projects/create", failOnStatusCode: false}).its('status').should('equal', 403)
        cy.request({url: "/projects/templates", failOnStatusCode: false}).its('status').should('equal', 403)

        // Now delete all created projects
        Cypress._.times(5, () => {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
               })
            })
        });
    })

    it("can give and revoke access to a project to another user", () => {
        // Names of projects and apps to create
        const project_name = "e2e-create-proj-test"
        const private_app_name = "e2e-private-app-test"
        const project_app_name = "e2e-project-app-test"
        const app_type = "Jupyter Lab"

        // Create a project
        cy.log("Now creating a project")
        cy.visit("/projects/")
        // Click button for UI to create a new project
        cy.get("a").contains('New project').click()
        // Next click button to create a new blank project
        cy.get("a").contains('Create').first().click()
        // Fill in the options for creating a new blank project
        cy.get('input[name=name]').type(project_name)
        cy.get('textarea[name=description]').type("A test project created by an e2e test.")
        cy.get("input[name=save]").contains('Create project').click()
        cy.wait(5000) // sometimes it takes a while to create a project

        // Create private app
        cy.log("Now creating a private app")
        cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
        cy.get('input[name=app_name]').type(private_app_name)
        cy.get('select[id=permission]').select('private')
        cy.get('button').contains('Create').click() // create app
        cy.get('tr:contains("' + private_app_name + '")').find('span').should('contain', 'private') // check that the app got greated

        // Create project app
        cy.log("Now creating a project app")
        cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
        cy.get('input[name=app_name]').type(project_app_name)
        cy.get('select[id=permission]').select('project')
        cy.get('button').contains('Create').click() // create app
        cy.get('tr:contains("' + project_app_name + '")').find('span').should('contain', 'project') // check that the app got greated

        // Give access to this project to a collaborator user
        cy.log("Now giving access to another user")
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
        cy.log("Now logging in as contributor's collaborator user")
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaUI(users.contributor_collaborator.email, users.contributor_collaborator.password)
        })

        // Check that the contributor's collaborator user has correct access
        cy.log("Now checking access to project and apps")
        cy.visit('/projects/')
        cy.get('h5.card-title').should('contain', project_name) // check access to project
        cy.get('a.btn').contains('Open').click()
        cy.get('tr:contains("' + private_app_name + '")').should('not.exist') // private app not visible
        // to be added: go to URL and check that it does not open
        cy.get('tr:contains("' + project_app_name + '")').should('exist') // project app visible
        // to be added: go to URL and check that it opens successfully

        // Log back in as contributor user
        cy.log("Now logging back in as contributor user")
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaApi(users.contributor.email, users.contributor.password)
        })

        // Remove access to the project
        cy.log("Now removing access from contributor's collaborator user")
        cy.visit('/projects/')
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('[data-cy="settings"]').click()
        cy.get('a[href="#access"]').click()
        cy.get('tr.user-with-access').find('button.btn-close').click()
        .then((href) => {
            cy.get('button.btn-danger').contains('Revoke').click()
        })

        // Log in as contributor's collaborator user
        cy.log("Now again logging in as contributor's collaborator user")
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaUI(users.contributor_collaborator.email, users.contributor_collaborator.password)
        })

        // Check that the contributor's collaborator user no longer has access to the project
        cy.log("Now checking that contributor's collaborator user no longer has access")
        cy.visit('/projects/')
        cy.get('h5.card-title').should('not.exist') // check visibility of project
        // to-do: save the url of the project in a previous step and check if possible to open that with a direct link

        // Log back in as contributor user
        cy.log("Now logging back in as contributor user")
        cy.fixture('users.json').then(function (data) {
            users = data
            cy.loginViaApi(users.contributor.email, users.contributor.password)
        })

        // Delete the created project
        cy.log("Now deleting the created project")
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
               })
            })
    })
})
