describe("Test superuser access", () => {

    // Tests performed as an authenticated user that has superuser privileges
    // user: no-reply-superuser@scilifelab.se

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
        cy.log("Running seed_superuser.py")
        cy.exec("./cypress/e2e/db-seed-superuser.sh")
    })

    beforeEach(() => {
        // email in fixture must match email in db-reset.sh
        cy.log("Logging in as superuser")
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.superuser.email, users.superuser.password)
        })
    })

    it("can see extra deployment options and extra settings in a project", () => {
        // Names of objects to create
        const project_name = "e2e-create-default-proj-test"
        const project_description = "A test project created by an e2e test."
        const project_description_2 = "An alternative project description created by an e2e test."

        cy.visit("/projects/")
        cy.get("title").should("have.text", "My projects | SciLifeLab Serve (beta)")

        cy.log("Creating a project as a superuser")
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

        cy.get('h3').should('contain', project_name)
        cy.get('.card-text').should('contain', project_description)

        cy.log("Checking that the correct deployment options are available (i.e. with extra deployment options)")
        cy.get('.card-header').find('h5').should('contain', 'Develop')
        cy.get('.card-header').find('h5').should('contain', 'Serve')
        cy.get('.card-body').find('h5').should('contain', 'Shiny App (single copy)')
        cy.get('.card-header').find('h5').should('contain', 'Additional options [admins only]')

        cy.log("Checking that project settings are available")
        cy.get('[data-cy="settings"]').click()
        cy.url().should("include", "settings")
        cy.get('h3').should('contain', 'Project settings')

        cy.log("Checking that the correct project settings are visible (i.e. with extra settings)")
        cy.get('.list-group').find('a').should('contain', 'Access')
        cy.get('.list-group').find('a').should('contain', 'S3 storage')
        cy.get('.list-group').find('a').should('contain', 'MLFlow')
        cy.get('.list-group').find('a').should('contain', 'Flavors')
        cy.get('.list-group').find('a').should('contain', 'Environments')

        cy.log("Changing project description")
        cy.get('textarea[name=description]').clear().type(project_description_2)
        cy.get('button').contains('Save').click()
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('.card-text').should('contain', project_description_2)

        cy.log("Deleting the project from the settings menu")
        cy.get('[data-cy="settings"]').click()
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

    it("can see and manipulate other users' projects and apps", () => {

        // Names of objects
        const project_name = "e2e-superuser-testuser-proj-test" // from seed_superuser.py
        const project_description ="Description by regular user" // from seed_superuser.py
        const project_description_2 = "An alternative project description created by an e2e test."
        const private_app_name = "Regular user's private app" // from seed_superuser.py
        const private_app_name_2 = "App renamed by superuser"

        cy.log("Verifying that a project of a regular user is visible")
        cy.visit("/projects/")
        cy.get('h5.card-title').should('contain', project_name)

        cy.log("Verifying that can edit the description of a project of a regular user")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('.card-text').should('contain', project_description)
        cy.get('[data-cy="settings"]').click()
        cy.get('textarea[name=description]').clear().type(project_description_2)
        cy.get('button').contains('Save').click()
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('.card-text').should('contain', project_description_2)

        cy.log("Verifying that a private app of a regular user is visible")
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
        cy.get('tr:contains("' + private_app_name + '")').should('exist') // regular user's private app visible

        cy.log("Verifying that can edit the private app of a regular user")
        cy.get('tr:contains("' + private_app_name + '")').find('i.bi-three-dots-vertical').click()
        cy.get('tr:contains("' + private_app_name + '")').find('a').contains('Settings').click()
        cy.get('input[name=app_name]').type(private_app_name_2) // change name
        cy.get('button').contains('Update').click()
        cy.get('tr:contains("' + private_app_name_2 + '")').should('exist') // regular user's private app now has a different name

        cy.log("Deleting a regular user's private app")
        cy.get('tr:contains("' + private_app_name_2 + '")').find('i.bi-three-dots-vertical').click()
        cy.get('tr:contains("' + private_app_name_2 + '")').find('a.confirm-delete').click()
        cy.get('button').contains('Delete').click()
        cy.wait(5000)
        cy.get('tr:contains("' + private_app_name_2 + '")').find('span').should('contain', 'Deleted')

        cy.log("Deleting a regular user's project")
        cy.visit("/projects/")
        cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
               })
            })

    })

    it("can create a persistent volume", () => {
        // Names of objects to create
        const project_name_pvc = "e2e-superuser-pvc-test"
        const volume_name = "e2e-project-vol"

        cy.log("Creating a blank project")
        cy.createBlankProject(project_name_pvc)

        cy.log("Creating a persistent volume")
        cy.visit("/projects/")
        cy.contains('.card-title', project_name_pvc).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

        cy.get('div.card-body:contains("Persistent Volume")').find('a:contains("Create")').click()
        cy.get('input[name=app_name]').type(volume_name)
        cy.get('button').contains('Create').click()
        cy.get('tr:contains("' + volume_name + '")').should('exist') // persistent volume has been created

        // This does not work in our CI. Disabled for now, needs to be enabled for runs against an instance of Serve running on the cluster
        /*
        cy.get('tr:contains("' + volume_name + '")').find('span').should('contain', 'Installed') // confirm the volume is working

        cy.log("Deleting the created persistent volume")
        cy.get('tr:contains("' + volume_name + '")').find('i.bi-three-dots-vertical').click()
        cy.get('tr:contains("' + volume_name + '")').find('a.confirm-delete').click()
        cy.get('button').contains('Delete').click()
        cy.get('tr:contains("' + volume_name + '")').find('span').should('contain', 'Deleted') // confirm the volume has been deleted
        */

        cy.log("Deleting the created project")
        cy.visit("/projects/")
        cy.contains('.card-title', project_name_pvc).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
        .then((href) => {
            cy.get('div#modalConfirmDelete').should('have.css', 'display', 'block')
            cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
                cy.contains(project_name_pvc).should('not.exist') // confirm the project has been deleted
           })
        })

    })

    it("can bypass N projects limit", () => {
        // Names of projects to create
        const project_name = "e2e-create-proj-test"

        cy.log("Create 5 projects (current limit for regular users)")
        Cypress._.times(5, () => {
            // better to write this out rather than use the createBlankProject command because then we can do a 5000 ms pause only once
            cy.visit("/projects/")
            cy.get("a").contains('New project').click()
            cy.get("a").contains('Create').first().click()
            cy.get('input[name=name]').type(project_name)
            cy.get("input[name=save]").contains('Create project').click()
        });
        cy.wait(5000) // sometimes it takes a while to create a project but just waiting once at the end should be enough

        cy.log("Check that it is still possible to click the button to create a new project")
        cy.visit("/projects/")
        cy.get("a").contains('New project').should('exist')

        cy.log("Create one more project to check it is possible to bypass the limit")
        cy.createBlankProject(project_name)
        cy.visit("/projects/")
        cy.get('h5:contains("' + project_name + '")').its('length').should('eq', 6) // check that the superuser now bypassed the limit for regular users

        cy.log("Now delete all created projects")
        Cypress._.times(6, () => {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
               })
            })
        });
    })

    it("can bypass N apps limit", () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test-apps-limit"
        const app_name = "e2e-create-jl"

         cy.log("Creating a blank project")
         cy.createBlankProject(project_name)
            .then(() => {
                cy.log("Create 3 jupyter lab instances (current limit)")
                Cypress._.times(3, () => {
                        cy.get('[data-cy="create-app-card"]').contains('Jupyter Lab').parent().siblings().find('.btn').click()
                        cy.get('input[name=app_name]').type(app_name)
                        cy.get('.btn-primary').contains('Create').click()
                });
                cy.log("Check that the button to create another one still works")
                cy.get('[data-cy="create-app-card"]').contains('Jupyter Lab').parent().siblings().find('.btn').should('have.attr', 'href')
                cy.log("Check that it is possible to create another one and therefore bypass the limit")
                cy.get('[data-cy="create-app-card"]').contains('Jupyter Lab').parent().siblings().find('.btn').click()
                cy.get('input[name=app_name]').type(app_name)
                cy.get('.btn-primary').contains('Create').click()
                cy.get('tr:contains("' + app_name + '")').its('length').should('eq', 4) // we now have an extra app
                })

         cy.log("Deleting the created project")
         cy.visit("/projects/")
         cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
         .then((href) => {
             cy.get('div#modalConfirmDelete').should('have.css', 'display', 'block')
             cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                 cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
                 cy.contains(project_name).should('not.exist') // confirm the project has been deleted
            })
         })


    })

})
