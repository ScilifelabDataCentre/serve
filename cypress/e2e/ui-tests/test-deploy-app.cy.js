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

    it("can create a standard app", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-create-proj-test"
        const app_name = "e2e-streamlit-example"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources');

        if (createResources === 'true') {
            cy.visit("/projects/")
            cy.get('div.card-body:contains("' + project_name + '")').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("Standard App")').find('a:contains("Create")').click()

            cy.get('input[name=app_name]').type(app_name)
            cy.get('input[name="appconfig.port"]').clear().type("8080")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('button').contains('Create').click()
            
            cy.get('tbody:contains("Standard App")').find('span').should('contain', 'Running')

            cy.get('tbody:contains("Standard App")').find('i.bi-three-dots-vertical').click()
            cy.get('tbody:contains("Standard App")').find('a.confirm-delete').click()
            
            cy.get('button').contains('Delete').click()
            cy.get('tbody:contains("Standard App")').find('span').should('contain', 'Deleted')
        } else {
            cy.log('Skipped because create_resources is not true');
      }
    })

})
