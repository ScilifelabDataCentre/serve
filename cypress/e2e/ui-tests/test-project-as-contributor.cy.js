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
        // username in fixture must match username in db-reset.sh
        cy.log("Logging in as contributor user")
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.contributor.username, users.contributor.password)
        })
    })


    it("can run the test setup", () => {
    })

    it("can create a new project with default template, open settings, delete from settings", { defaultCommandTimeout: 100000 }, () => {

        // Names of objects to create
        const project_name = "e2e-create-default-proj-test"
        const project_title_name = project_name + " | SciLifeLab Serve"

        cy.visit("/projects/")
        cy.get("title").should("have.text", "My projects | SciLifeLab Serve")

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

    // This test cannot run properly in GitHub workflows because there is an issue with minio creation there. Therefore, it should be run locally to make sure things work. For GitHub, skipping it.
    it.skip("can create a new project with ML serving template, open settings, delete from settings", { defaultCommandTimeout: 100000 }, () => {

        // Names of objects to create
        const project_name = "e2e-create-ml-proj-test"
        const project_title_name = project_name + " | SciLifeLab Serve"

        cy.visit("/projects/")
        cy.get("title").should("have.text", "My projects | SciLifeLab Serve")

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
    })
})
