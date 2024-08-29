describe("Test deploying app", () => {

    // Tests performed as an authenticated user that
    // creates and deletes apps.
    // user: e2e_tests_deploy_app_user

    let users

    before({ defaultCommandTimeout: 100000 }, () => {
        cy.logf("Begin before() hook", Cypress.currentTest)

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
        cy.logf("Running seed-deploy-app-user.py", Cypress.currentTest)
        cy.exec("./cypress/e2e/db-seed-deploy-app-user.sh")
        // username in fixture must match username in db-reset.sh
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password)
        })
        const project_name = "e2e-deploy-app-test"
        cy.createBlankProject(project_name)

        cy.logf("End before() hook", Cypress.currentTest)
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)

        // username in fixture must match username in db-reset.sh
        cy.logf("Logging in", Cypress.currentTest)
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password)
        })

        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("can deploy a project and public app using the custom app chart", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name_project = "e2e-streamlit-example-project"
        const app_name_public = "e2e-streamlit-example-public"
        const app_name_public_2 = "e2e-streamlit-example-2-public"
        const app_description = "e2e-streamlit-description"
        const app_description_2 = "e2e-streamlit-2-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const image_name_2 = "ghcr.io/scilifelabdatacentre/example-streamlit:230921-1443"
        const image_port = "8501"
        const image_port_2 = "8502"
        const app_path = "/home/username"
        const app_path_2 = "/home/username/app"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"
        const app_source_code_public = "https://doi.org/example"

        let volume_display_text = "project-vol (" + project_name + ")"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with project permissions
            cy.logf("Now creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_project)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            cy.get('#id_volume').select(volume_display_text)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_path').clear().type(app_path)
            cy.get('#submit-id-submit').contains('Submit').click()
            // check that the app was created
            cy.get('tr:contains("' + app_name_project + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name_project + '")').find('span').should('contain', 'project')
            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').contains(app_name_project).should('not.exist')

            // make this app public as an update and check that it works
            cy.logf("Now making the project app public", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_project + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_project + '")').find('a').contains('Settings').click()
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.get('#submit-id-submit').contains('Submit').click()
            cy.get('tr:contains("' + app_name_project + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name_project + '")').find('span').should('contain', 'public')

            cy.logf("Now deleting the project app (by now public)", Cypress.currentTest)
            cy.get('tr:contains("' + app_name_project + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_project + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tr:contains("' + app_name_project + '")').find('span').should('contain', 'Deleted')

            // Create a public app and verify that it is displayed on the public apps page
            cy.logf("Now creating a public app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_public)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(app_source_code_public)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_path').clear().type(app_path)
            cy.get('#id_volume').select(volume_display_text)
            cy.get('#submit-id-submit').contains('Submit').click()

            cy.get('tr:contains("' + app_name_public + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name_public + '")').find('span').should('contain', 'public')

            cy.visit("/apps")
            cy.get('h5.card-title').should('contain', app_name_public)
            cy.get('.card-text').find('p').should('contain', app_description)

            // Check that the public app is displayed on the homepage
            cy.logf("Now checking if the public app is displayed when not logged in.", Cypress.currentTest)
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

            // Check that the logs page opens for the app
            cy.logf("Now checking that the logs page for the app opens", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public + '")').find('a').contains('Logs').click()
            cy.get('h3').should('contain', "Logs")

            // Try changing the name, description, etc. of the app and verify it works
            cy.logf("Now changing the name and description of the public app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_public) // name should be same as before
            cy.get('#id_name').clear().type(app_name_public_2) // now change name
            cy.get('#id_description').should('have.value', app_description) // description should be same as set before
            cy.get('#id_description').clear().type(app_description_2) // now change description
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            // checking that a) permissions can be changed to 'Link'; b) that the corresponding text field is shown and mandatory
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').should('be.visible')
            cy.get('#id_note_on_linkonly_privacy').clear().type(link_privacy_type_note)
            cy.get('#id_volume').find(':selected').should('contain', 'project-vol')
            cy.get('#id_port').should('have.value', image_port)
            cy.get('#id_port').clear().type(image_port_2)
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_image').clear().type(image_name_2)
            cy.get('#id_path').should('have.value', app_path)
            cy.get('#id_path').clear().type(app_path_2)
            cy.get('#submit-id-submit').contains('Submit').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('span').should('contain', 'link')
            cy.get('tr:contains("' + app_name_public_2 + '")').find('span').should('contain', 'Running') // NB: it will get status "Running" but it won't work because the new port is incorrect
            // Check that the changes were saved
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_public_2)
            cy.get('#id_description').should('have.value', app_description_2)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_note_on_linkonly_privacy').should('have.value', link_privacy_type_note)
            cy.get('#id_port').should('have.value', image_port_2)
            cy.get('#id_image').should('have.value', image_name_2)
            cy.get('#id_path').should('have.value', app_path_2)

            // Remove the created public app and verify that it is deleted from public apps page
            cy.logf("Now deleting the public app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tr:contains("' + app_name_public_2 + '")').find('span').should('contain', 'Deleted')
            // check that the app is not visible under public apps
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').contains(app_name_public_2).should('not.exist')
        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    // This test is skipped because it will only work against a Serve instance running on our cluster. should be switched on for the e2e tests against remote.
    it.skip("can deploy a shiny app", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-shiny-example"
        const app_description = "e2e-shiny-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/shiny-adhd-medication-sweden:20240117-062031"
        const image_port = "3838"
        const createResources = Cypress.env('create_resources');
        const app_type = "Shiny App"

        if (createResources === true) {
            cy.logf("Creating a shiny app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
        //    cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'Running') // for now commented out because it takes shinyproxy a really long time to start up and therefore status "Running" can take 5 minutes to show up
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'public')

            cy.logf("Checking that all shiny app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            cy.logf("Checking that the shiny app is displayed on the public apps page", Cypress.currentTest)
            cy.visit("/apps")
            cy.get('h5.card-title').should('contain', app_name)
            cy.get('.card-text').find('p').should('contain', app_description)

            cy.logf("Checking that instructions for running the app locally are displayed on public apps page", Cypress.currentTest)
            cy.get('a[data-bs-target="#dockerInfoModal"]').click()
            cy.get('div#dockerInfoModal').should('be.visible')
            cy.get('code').first().should('contain', image_name)
            cy.get('code').first().should('contain', image_port)
            cy.get('div.modal-footer').find('button').contains('Close').click()

            cy.logf("Checking that source code URL is displayed on the public apps page", Cypress.currentTest)
            cy.visit("/apps")
            cy.get('a#source-code-url').should('have.attr', 'href', source_code_url)

            cy.logf("Deleting the shiny app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'Deleted')
            // check that the app is not visible under public apps
            cy.visit("/apps")
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').contains(app_name).should('not.exist')
        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can deploy a dash app", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-dash-example"
        const app_name_edited = "e2e-dash-example-edited"
        const app_description = "e2e-dash-description"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources');
        const app_type = "Dash App"

        if (createResources === true) {
            // Create Dash app
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').contains('Submit').click()
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'public')
            cy.get('tr:contains("' + app_name + '")', {timeout: 100000}).find('span').should('contain', 'Running')

            // Verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // Edit Dash app
            cy.logf("Editing the dash app settings (non redeployment fields)", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()

            cy.get('#id_name').type("-edited")
            cy.get('#submit-id-submit').contains('Submit').click()
            // Verify that the app status still equals Running
            cy.get('tr:contains("' + app_name_edited + '")').find('span').should('contain', 'public')
            cy.get('tr:contains("' + app_name_edited + '")', {timeout: 100000}).find('span').should('contain', 'Running')

            // Delete the Dash app
            cy.logf("Deleting the dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_edited + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_edited + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tr:contains("' + app_name_edited + '")').find('span').should('contain', 'Deleted')

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').contains(app_name_edited).should('not.exist')
        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can deploy a tissuumaps app", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-tissuumaps-example"
        const app_description = "e2e-tissuumaps-description"
        const createResources = Cypress.env('create_resources');
        const app_type = "TissUUmaps App"

        let volume_display_text = "project-vol (" + project_name + ")"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            cy.logf("Creating a tisuumaps app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Public')
            cy.get('#id_volume').select(volume_display_text)
            cy.get('#submit-id-submit').contains('Submit').click()
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'public')

            cy.logf("Checking that all tissuumaps app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Public')
            cy.get('#id_volume').find(':selected').should('contain', 'project-vol')

            cy.logf("Deleting the tissuumaps app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').contains('Delete').click()
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'Deleted')

            // check that the app is not visible under public apps
            cy.visit('/apps/')
            cy.get("title").should("have.text", "Apps | SciLifeLab Serve (beta)")
            cy.get('h3').should('contain', 'Public apps')
            cy.get('h5.card-title').contains(app_name).should('not.exist')
        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    it("can set and change custom subdomain", { defaultCommandTimeout: 100000 }, () => {
        // Names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-subdomain-example"
        const app_name_2 = "e2e-second-subdomain-example"
        const app_description = "e2e-subdomain-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources');
        const app_type = "Custom App"
        const subdomain = "subdomain-test"
        const subdomain_2 = "subdomain-test2"
        const subdomain_3 = "subdomain-test3"

        let volume_display_text = "project-vol (" + project_name + ")"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            // Create an app and set a custom subdomain for it
            cy.logf("Now creating an app with a custom subdomain", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            // fill out other fields
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_port').clear().type("8501")
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_volume').select(volume_display_text)
            cy.get('#id_path').clear().type("/home")
            // fill out subdomain field
            cy.get('#id_subdomain').type(subdomain)

            // create the app
            cy.get('#submit-id-submit').contains('Submit').click()
            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain)

            // Try using the same subdomain the second time
            cy.logf("Now trying to create an app with an already taken subdomain", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()

            cy.get('#id_name').type(app_name_2)
            cy.get('#id_port').clear().type("8501")
            cy.get('#id_image').clear().type(image_name)

            // fill out subdomain field
            cy.get('#id_subdomain').type(subdomain)
            cy.get('#id_subdomain').blur();
            cy.get('#div_id_subdomain').should('contain.text', 'The subdomain is not available');


            cy.get('#id_subdomain').clear().type(subdomain_2)
            cy.get('#id_subdomain').blur();
            cy.get('#div_id_subdomain').should('contain.text', 'The subdomain is available');
            // create the app
            cy.get('#submit-id-submit').contains('Submit').click()
            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name_2).should('have.attr', 'href').and('include', subdomain_2)

            // Change subdomain of a previously created app
            cy.logf("Now changing subdomain of an already created app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains("Settings").click()
            cy.get('#id_subdomain').type(subdomain_3)

            cy.get('#submit-id-submit').contains('Submit').click()
            // check that the app was updated with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain_3)

            // Verify that the app status is not Deleted (Deleting and Created ok)
            cy.get('tr:contains("' + app_name + '")', {timeout: 5000}).find('span').should('not.contain', 'Deleted')
            // Finally verify status equals Running
            cy.get('tr:contains("' + app_name + '")', {timeout: 100000}).find('span').should('contain', 'Running')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

    // this test is skipped now because app statuses do not work as expected in the CI; needs to be enabled when running against a running dev instance
    it.skip("see correct statuses when deploying apps", {}, () => {
        // These tests are to check that the event listener works as expected

        const createResources = Cypress.env('create_resources');
        const project_name = "e2e-deploy-app-test"
        const app_name_statuses = "e2e-app-statuses"
        const app_description = "e2e-subdomain-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const app_type = "Custom App"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // Create an app with project permissions
            cy.logf("Now creating an app with a non-existent image reference - expecting Image Error", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_statuses)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            cy.get('#id_port').type("8501")
            cy.get('#id_image').type("hkqxqxkhkqwxhkxwh") // input random string
            cy.get('#submit-id-submit').contains('Submit').click()
            // Check that the app was created. Using custom timeout of 5 secs
            cy.get('tr:contains("' + app_name_statuses + '")', {timeout: 5000}).find('span').should('contain', 'Image Error')
            cy.logf("Now updating the app to give a correct image reference - expecting Running", Cypress.currentTest)
            cy.get('tr:contains("' + app_name_statuses + '")').find('i.bi-three-dots-vertical').click()
            cy.get('tr:contains("' + app_name_statuses + '")').find('a').contains('Settings').click()
            cy.get('#id_image').clear().type(image_name)
            cy.get('#submit-id-submit').contains('Submit').click()
            // Using longer custom timeout for correct image to be set to Running
            cy.get('tr:contains("' + app_name_statuses + '")', {timeout: 30000}).find('span').should('contain', 'Running')
        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest);
      }
    })

})
