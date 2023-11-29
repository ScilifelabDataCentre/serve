describe("Test deploying app", () => {

    // Tests performed as an authenticated user that
    // creates and deletes objects.
    // user: e2e_tests_deploy_app_user

    let users

    before({ defaultCommandTimeout: 100000 }, () => {
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
        cy.log("Running seed-deploy-app-user.py")
        cy.exec("./cypress/e2e/db-seed-deploy-app-user.sh")
        // username in fixture must match username in db-reset.sh
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password)
        })
        const project_name = "e2e-deploy-app-test"
        cy.createBlankProject(project_name)
    })

    beforeEach(() => {
        // username in fixture must match username in db-reset.sh
        cy.log("Logging in")
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password)
        })
    })

    it("can deploy a private and public app", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name_public = "e2e-streamlit-example-public"
        const app_name_public_2 = "e2e-streamlit-example-2-public"
        const app_name_private = "e2e-streamlit-example-private"
        const app_description = "e2e-streamlit-description"
        const app_description_2 = "e2e-streamlit-2-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with private or project permissions
            cy.log("Now creating a private or project app")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('input[name=app_name]').type(app_name_private)
            cy.get('textarea[name=app_description]').type(app_description)
            cy.get('input[name="appconfig.port"]').clear().type("8501")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('input[name="appconfig.path"]').clear().type("/home")
            cy.get('button').contains('Create').click()
            // check that the app was created
            cy.get('tr:contains("' + app_name_private + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name_private + '")').find('span').should('contain', 'project')
            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').should('not.exist')

            // make this app public as an update and check that it works
            cy.log("Now making the private or project app public")
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_private + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_private + '")').find('a').contains('Settings').click()
            cy.get('#permission').select('public')
            cy.get('button').contains('Update').click()
            cy.get('tr:contains("' + app_name_private + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name_private + '")').find('span').should('contain', 'public')

            cy.log("Now deleting the private or project app (by now public)")
            cy.get('tr:contains("' + app_name_private + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_private + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tr:contains("' + app_name_private + '")').find('span').should('contain', 'Deleted')

            // Create a public app and verify that it is displayed on the public apps page
            cy.log("Now creating a public app")
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('input[name=app_name]').type(app_name_public)
            cy.get('textarea[name=app_description]').type(app_description)
            cy.get('#permission').select('public')
            cy.get('input[name="appconfig.port"]').clear().type("8501")
            cy.get('input[name="appconfig.image"]').clear().type(image_name)
            cy.get('input[name="appconfig.path"]').clear().type("/home")
            cy.get('button').contains('Create').click()

            cy.get('tr:contains("' + app_name_public + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name_public + '")').find('span').should('contain', 'public')

            cy.visit("/apps")
            cy.get('h5.card-title').should('contain', app_name_public)
            cy.get('.card-text').find('p').should('contain', app_description)

            // Check that the public app is displayed on the homepage
            cy.log("Now checking if the public app is displayed when not logged in.")
            cy.visit("/home/")
            cy.get('h5').should('contain', app_name_public)
            // Log out and check that the public app is still displayed on the homepage
            cy.clearCookies();
            cy.clearLocalStorage();
            Cypress.session.clearAllSavedSessions()
            cy.visit('/projects/')
            cy.get('h3').should('contain', 'Login required') // check that logout worked
            cy.visit("/")
            cy.get('h5').should('contain', app_name_public)
            // Log back in
            cy.fixture('users.json').then(function (data) {
                users = data
                cy.loginViaUI(users.deploy_app_user.email, users.deploy_app_user.password)
            })

            // Try changing the name and description of the app and verify it works
            cy.log("Now changing the name and description of the public app")
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public + '")').find('a').contains('Settings').click()
            cy.get('input[name=app_name]').clear().type(app_name_public_2)
            cy.get('textarea[name=app_description]').clear().type(app_description_2)
            cy.get('button').contains('Update').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name_public_2 + '")').find('span').should('contain', 'public')
            cy.visit("/apps")
            cy.get('h5.card-title').should('contain', app_name_public_2)
            cy.get('.card-text').find('p').should('contain', app_description_2)

            // To be added: changing of image, port, flavor, pvc, path in pvc (can at least check if it works to change in DB)

            // Remove the created public app and verify that it is deleted from public apps page
            cy.log("Now deleting the public app")
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('span').should('contain', 'Deleted')
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').should('not.exist')

        } else {
            cy.log('Skipped because create_resources is not true');
      }
    })

    it("can set and change custom subdomain", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
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
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains("Settings").click()
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
