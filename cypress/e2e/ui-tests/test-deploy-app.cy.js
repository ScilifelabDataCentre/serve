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
    })

    beforeEach(() => {
        // username in fixture must match username in db-reset.sh
        cy.log("Logging in as contributor user")
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.contributor.username, users.contributor.password)
        })
        const project_name = "e2e-create-proj-test"
        cy.createBlankProject(project_name)

    })

    it("can deploy a private and public app", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test"
        const app_name = "e2e-streamlit-example"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.get('div.card-body:contains("' + project_name + '")').find('a:contains("Open")').first().click()

            // Create an app with private or project permissions
            cy.log("Now creating a private or project app")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()

            cy.get('input[name=app_name]').type(app_name)
            cy.get('input[name="appconfig.port"]').clear().type("8080")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('button').contains('Create').click()

            cy.get('tbody:contains("' + app_type + '")').find('span').should('contain', 'Running')

            cy.get('tbody:contains("' + app_type + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tbody:contains("' + app_type + '")').find('a.confirm-delete').click()

            cy.get('button').contains('Delete').click()
            cy.get('tbody:contains("' + app_type + '")').find('span').should('contain', 'Deleted')

            // Create a public app and verify that it is displayed on the public apps page
            cy.log("Now creating a public app")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()

            cy.get('input[name=app_name]').type(app_name)
            cy.get('#permission').select('public')
            cy.get('input[name="appconfig.port"]').clear().type("8080")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('button').contains('Create').click()

            cy.get('tbody:contains("' + app_type + '")').find('span').should('contain', 'Running')

            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').contains(app_name).parents('div.card-body')
                .find('span.badge').should("have.text", "Running")

        } else {
            cy.log('Skipped because create_resources is not true');
      }
    })

})
