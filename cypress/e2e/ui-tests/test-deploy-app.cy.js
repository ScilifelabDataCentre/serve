describe("Test deploying app", () => {

    // Tests performed as an authenticated user that
    // creates and deletes objects.
    // user: e2e_tests_contributor_tester

    let users

    before({ defaultCommandTimeout: 100000 }, () => {
        // seed the db with: contributor user, a blank project
        cy.log("Seeding the db for the contributor tests. Running db-seed-contributor.sh");
        cy.exec("./cypress/e2e/db-reset.sh")
        cy.wait(60000)
        cy.visit("/")
        cy.log("Running seed_contributor.py")
        cy.exec("./cypress/e2e/db-seed-contributor.sh")
        // username in fixture must match username in db-reset.sh
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.contributor.username, users.contributor.password)
        })
        const project_name = "e2e-create-proj-test"
        cy.createBlankProject(project_name)
    })

    beforeEach(() => {
        // username in fixture must match username in db-reset.sh
        cy.log("Logging in as contributor user")
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.contributor.username, users.contributor.password)
        })
    })

    it("can deploy a private and public app", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test"
        const app_name = "e2e-streamlit-example"
        const app_description = "e2e-streamlit-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            // Create an app with private or project permissions
            cy.log("Now creating a private or project app")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()

            cy.get('input[name=app_name]').type(app_name)
            cy.get('textarea[name=app_description]').type(app_description)
            cy.get('input[name="appconfig.port"]').clear().type("8501")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('input[name="appconfig.path"]').clear().type("/home")
            cy.get('button').contains('Create').click()

            // TODO: debug problems with status not set to Running
            //cy.get('tbody:contains("' + app_type + '")').find('span').should('contain', 'Running')

            cy.get('tbody:contains("' + app_type + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tbody:contains("' + app_type + '")').find('a.confirm-delete').click()

            cy.get('button').contains('Delete').click()
            cy.get('tbody:contains("' + app_type + '")').find('span').should('contain', 'Deleted')

            // Create a public app and verify that it is displayed on the public apps page
            cy.log("Now creating a public app")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()

            cy.get('input[name=app_name]').type(app_name)
            cy.get('textarea[name=app_description]').type(app_description)
            cy.get('#permission').select('public')
            cy.get('input[name="appconfig.port"]').clear().type("8501")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('input[name="appconfig.path"]').clear().type("/home")
            cy.get('button').contains('Create').click()

            // TODO: debug problems with status not set to Running
            //cy.get('tbody:contains("' + app_type + '")').find('span').should('contain', 'Running')

            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').should('contain', app_name)

            //cy.get('h5.card-title').contains(app_name).parents('div.card-body')
            //    .find('span.badge').should("have.text", "Running")

            // Remove the created public app and verify that it is deleted from public apps page
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tbody:contains("' + app_type + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tbody:contains("' + app_type + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tbody:contains("' + app_type + '")').find('span').should('contain', 'Deleted')
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').should('not.exist')

        } else {
            cy.log('Skipped because create_resources is not true');
      }
    })

    it("can set and change custom subdomain", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test"
        const app_name = "e2e-subdomain-example"
        const app_description = "e2e-subdomain-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"
        const subdomain = "subdomain-test"
        const subdomain_2 = "subdomain-test2"
        const subdomain_3 = "subdomain-test3"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            // Create an app and set a custom subdomain for it
            cy.log("Now creating an app with a custom subdomain")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            // fill out other fields
            cy.get('input[name=app_name]').type(app_name)
            cy.get('textarea[name=app_description]').type(app_description)
            cy.get('input[name="appconfig.port"]').clear().type("8501")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('input[name="appconfig.path"]').clear().type("/home")
            // fill out subdomain field
            cy.get('[id="subdomain"]').find('button').click()
            cy.get('[id="subdomain-add"]').find('[id="rn"]').type(subdomain)
            cy.get('[id="subdomain-add"]').find('button').click()
            cy.wait(5000)
            cy.get('[id="subdomain"]').find('select#app_release_name option:selected').should('contain', subdomain)
            // create the app
            cy.get('button').contains('Create').click()
            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain)

            // Try using the same subdomain the second time
            cy.log("Now trying to create an app with an already taken subdomain")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            // fill out subdomain field
            cy.get('[id="subdomain"]').find('button').click()
            cy.get('[id="subdomain-add"]').find('[id="rn"]').type(subdomain)
            cy.get('[id="subdomain-add"]').find('button').click()
            cy.wait(5000)
            cy.get('[id="subdomain-add"]').find('[id="subdomain-invalid"]').should('be.visible') // display errror when same subdomain
            cy.get('[id="subdomain-add"]').find('[id="rn"]').clear().type(subdomain_2)
            cy.get('[id="subdomain-add"]').find('button').click()
            cy.wait(5000)
            cy.get('[id="subdomain-add"]').find('[id="subdomain-invalid"]').should('not.be.visible') // do not display error when different subdomain
            cy.get('[id="subdomain"]').find('select#app_release_name option:selected').should('contain', subdomain_2) // and the newly added subdomain as selected again

            // Change subdomain of a previously created app
            cy.log("Now changing subdomain of an already created app")
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tbody:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tbody:contains("' + app_name + '")').find('a').contains("Settings").click()
            cy.get('[id="subdomain"]').find('button').click()
            cy.get('[id="subdomain-add"]').find('[id="rn"]').type(subdomain_3)
            cy.get('[id="subdomain-add"]').find('button').click()
            cy.wait(5000)
            // update the app
            cy.get('button').contains('Update').click()
            // check that the app was updated with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain_3)

        } else {
            cy.log('Skipped because create_resources is not true');
      }
    })

})