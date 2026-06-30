describe("Test deploying app", () => {

    // Integration tests
    // This test class tests the integration between Serve, InvenioRDM, k8s.
    // Hence, Serve needs to run with DOI minting NOT in mock mode.

    // Tests performed as an authenticated user that creates and deletes apps.
    // Note that these tests may depend on k8s deployments and may be long-running tests.
    // Warning: some of these tests may intermittenly fail depending on the available
    // resources if run in CI.

    // The default command timeout should not be so long
    // Instead use longer timeouts on specific commands where deemed necessary and valid
    const defaultCmdTimeoutMs = 10000
    // The longer timeout is often used when waiting for k8s operations to complete
    const longCmdTimeoutMs = 60000
    // Shiny apps have a longer timeout because of special treatment,
    // such as URL probing in the event-listener. Using timeout just over 3 minutes
    const shinyAppCmdTimeoutMs = 183000

    // Function to verify the displayed app status
    // Function to verify the displayed app permission level
    // Function to verify the expected_latest_user_action from data-app-action
    // Function to verify the expected_k8s_app_status from data-k8s-app-status

   const verifyAppStatus = (
    app_name,
    expected_status,
    expected_latest_user_action,
    expected_data_k8s_app_status,
    expected_permission,
    timeout = longCmdTimeoutMs,  // the caller can override the default long timeout
) => {
    // find the application row with timeout
    cy.contains('a', app_name, { timeout: defaultCmdTimeoutMs })
        .closest('tr')
        .within(() => {

            // verify application status with explicit timeout
            if (expected_status != "") {
                cy.get('[data-cy="appstatus"]', { timeout: timeout })
                    .should('have.attr', 'title', expected_status)
            }

            // verify latest user action if specified with explicit timeout
            // this action should be nearly immediate so here we use the shorter default timeout
            if (expected_latest_user_action != "") {
                cy.get('[data-cy="appstatus"]', { timeout: defaultCmdTimeoutMs })
                    .should('have.attr', 'data-app-action', expected_latest_user_action)
            }

            // verify data-k8s-app-status if specified with explicit timeout
            if (expected_data_k8s_app_status != "") {
                cy.get('[data-cy="appstatus"]', { timeout: timeout })
                    .should('have.attr', 'data-k8s-app-status', expected_data_k8s_app_status)
            }

            // verify permission level if specified with explicit timeout
            // this action should be nearly immediate so here we use the shorter default timeout
            if (expected_permission != "") {
                cy.get('[data-cy="app-permission"]', { timeout: defaultCmdTimeoutMs })
                    .should('contain', expected_permission)
            }
        });
};
    // If any previous test is failed then that app will remain.
    // this may fail the next test too.
    // So, before starting a next test, we are ensuring
    // one more time that the previous app is deleted.
    const deleteAppIfExists = (app_name, project_name) => {

        cy.fixture('users.json').then(function (data) {
            cy.loginViaApi(data.superuser.email, data.superuser.password)

            cy.visit("/projects/");

            cy.contains('.card-title', project_name)
                .parents('.card-body')
                .siblings('.card-footer')
                .find('a:contains("Open")')
                .first()
                .click();

            // check if app exists
            cy.get('body').then(($body) => {
                if ($body.find(`tr:contains("${app_name}")`).length) {
                    cy.log(`Deleting existing app as superuser: ${app_name}`);

                    // delete workflow
                    cy.get(`tr:contains("${app_name}")`)
                        .should('be.visible')
                        .find('i.ellipsis.vertical.icon')
                        .click();

                    cy.get(`tr:contains("${app_name}")`)
                        .should('be.visible')
                        .find('a.confirm-delete')
                        .click();

                    cy.get('button').should('be.visible').contains('Delete').click();

                    // verify deletion
                    cy.contains(`tr:contains("${app_name}")`).should('not.exist');
                    cy.log(`Successfully deleted app: ${app_name}`);
                }
                else {
                    cy.log(`No app named "${app_name}" found - skipping deletion`);
                }
            });

            cy.loginViaApi(data.deploy_app_user.email, data.deploy_app_user.password)
        });
    };


    // user: e2e_tests_deploy_app_user
    let users
    let TEST_USER_DATA
    let TEST_SUPERUSER_DATA
    const TEST_PROJECT_DATA = {
        project_name: "e2e-deploy-app-test",
        project_description: "e2e-deploy-app-test-desc",
    };


    before({ defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
        cy.logf("Begin before() hook", Cypress.currentTest)

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
                cy.log("Populating test data via Django endpoint");
                cy.fixture('users.json').then(function (data) {
                    TEST_USER_DATA = data.deploy_app_user
                    TEST_SUPERUSER_DATA = data.superuser
                    cy.populateTestUser(TEST_USER_DATA)
                    cy.populateTestSuperUser(TEST_SUPERUSER_DATA)
                    cy.populateTestProject(TEST_USER_DATA, TEST_PROJECT_DATA)
                })
            }

        else {

            // do db reset if needed
            if (Cypress.env('do_reset_db') === true) {
                cy.logf("Resetting db state. Running db-reset.sh", Cypress.currentTest)
                cy.exec("./cypress/e2e/db-reset.sh")
                cy.wait(Cypress.env('wait_db_reset'))
            }
            else {
                cy.logf("Skipping resetting the db state.", Cypress.currentTest)
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
        }


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

    it("can deploy a project and link app using the custom app chart", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name_project = "e2e-custom-example-project"
        const app_name_link = "e2e-custom-example-link"
        const app_name_link_2 = "e2e-custom-example-2-link"
        const app_description = "e2e-custom-description"
        const app_description_2 = "e2e-custom-2-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const image_name_2 = "ghcr.io/scilifelabdatacentre/example-streamlit:230921-1443"
        const image_port = "8501"
        const image_port_2 = "8502"
        const mount_path = "/home/data (project-vol (e2e-deploy-app-test))"
        const mount_path_2 = "/srv/shiny-server/data (project-vol (e2e-deploy-app-test))"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const createResources = Cypress.env('create_resources')
        const app_type = "Custom App"
        const default_url_subpath = "default/url/subpath/"
        const changed_default_url_subpath = "changed/subpath/"
        const invalid_default_url_subpath = "€% / ()"
        const keyword = "Microscopy"
        const keyword_two = "COVID-19"
        const creator_firstname = "First"
        const creator_lastname = "Last"
        const creator_affiliation = "Uppsala University"
        const funder_number = "0000-1234"
        const funder_org = "Swedish Research Council"
        const funder_number_two = "9999991"
        const funder_org_two = "Dutch Research Council"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // create an app with project permissions
            cy.logf("Now creating a project app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_project)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            // Verify storage management link
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');


            // Set mount path (replaces old volume and path fields) - it's a select dropdown
            cy.get('#id_mount_path').select('/home/data (project-vol (e2e-deploy-app-test))')

            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            // Advanced settings section is always open, so we can directly access the field
            // Scroll to the field to ensure it's in view
            cy.get('#id_default_url_subpath').scrollIntoView().should('be.visible')
            cy.get('#id_default_url_subpath').clear().type(default_url_subpath) // provide default_url_subpath
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // check that the app was created
            verifyAppStatus(app_name_project, "Running", "Creating", "Running", "Project")

            // check that the default URL subpath was created
            cy.contains('a', app_name_project)
                  .should('have.attr', 'href')
                  .and('include', default_url_subpath)
            // check that the app is not visible under public apps
            cy.visit('/apps/')
            // verify heading with correct text and encoding
            cy.get('[data-cy="apps-status-title"]').should('contain', 'Applications & models')
            cy.contains('h4.card-title', app_name_project).should('not.exist')

            // verify empty state when no apps exist
            // cy.get('.tag-list').should('be.empty');
            cy.contains('h4.card-title', app_name_project).should('not.exist')

            // make this app Link as an update and check that it works
            cy.logf("Now making the project app Link", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_project + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_project + '")').find('a').contains('Settings').click()
            // checking that a) permissions can be changed to 'Link'; b) that the corresponding text field is shown and mandatory
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').should('be.visible')
            cy.get('#id_note_on_linkonly_privacy').clear().type(link_privacy_type_note)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()
            verifyAppStatus(app_name_project, "Running", "Changing", "Running", "Link")

            // wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
                verifyAppStatus(app_name_project,  "Running", "Changing", "Running", "Link")
            })

            cy.logf("Now deleting the project app (by now Link)", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_project + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_project + '")').find('a.confirm-delete').click()
            cy.get('button').should('be.visible').contains('Delete').click()

            // verify deletion
            // give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_project + '")').should('not.exist')
            })

            // create a link app
            cy.logf("Now creating a link app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_link)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_mount_path').select(mount_path)
            cy.get('#div_id_invenio_tags').should('be.visible')
                .within(() => {
                    cy.get('input[placeholder*="Start typing"]').should('be.visible').type(keyword)
                    cy.get('.dropdown-menu .dropdown-item', { timeout: 10000 }).should('be.visible').first().should('have.text', keyword).click()
                })
            // make sure that the extra fields for public apps are visible and work
            cy.get('#id_language').should('be.visible').within(() => {
                cy.get('option').eq(0).should('have.value', 'eng').and('contain', 'English')
                cy.get('option').eq(1).should('have.value', 'swe').and('contain', 'Swedish')
                cy.get('option').eq(2).should('have.value', 'und').and('contain', 'Other')
            })
            cy.get('#id_language').select('swe')
            // add a creator manually
            cy.contains('button', 'Add creator').should('be.visible').click()
            cy.contains('.modal-content', 'Add creator')
                .should('be.visible')
                .within(() => {
                    cy.get('#newCreatorName').type(creator_firstname).should('have.value', creator_firstname)
                    cy.get('#newCreatorLastName').type(creator_lastname).should('have.value', creator_lastname)
                    cy.get('#newCreatorAffiliation').should('be.visible').type(creator_affiliation)
                    cy.get('#affiliationSuggestions', { timeout: 10000 }).should('be.visible').contains(creator_affiliation)
                    cy.get('#affiliationSuggestions .list-group-item').first().click()
                    cy.get('#saveCreatorBtn').should('not.be.disabled').click()
                })
            cy.get('#creatorsSortableList').should('exist').and('be.visible').find('li').eq(1)
                .should('contain', creator_firstname).and('contain', creator_lastname).and('contain', creator_affiliation)
            // add a creator using autopopulation from ORCID feature
            cy.contains('button', 'Add creator').should('be.visible').click()
            cy.contains('.modal-content', 'Add creator')
                .should('be.visible')
                .within(() => {
                    cy.get('#newCreatorOrcid').should('be.visible').type('Jane Doe')
                    cy.get('#orcidSuggestions .list-group-item', { timeout: 10000 }).should('be.visible').first().should('contain', 'Jane Doe').click()
                    cy.get('#newCreatorOrcid').should('have.value', 'https://orcid.org/0000-0002-1584-4316')
                    cy.get('#newCreatorAffiliation').should('have.value', 'Example Research Institute')
                    cy.get('#newCreatorName').should('have.value', 'Jane')
                    cy.get('#newCreatorLastName').should('have.value', 'Doe')
                    cy.get('#saveCreatorBtn').should('not.be.disabled').click()
                    })
            cy.get('#creatorsSortableList').should('exist').and('be.visible').find('li').eq(2)
                .should('contain', "Jane")
                .and('contain', "Doe")
                .and('contain', "Example Research Institute")
                .and('contain', "https://orcid.org/0000-0002-1584-4316")
            // add funding info
            cy.get('#addFunderBtn').should('be.visible').click()
            cy.contains('.modal-content', 'Add funder')
                .should('be.visible')
                .within(() => {
                    cy.get('#awardNumberInput').should('be.visible').type(funder_number)
                    cy.get('#funderNameInput').should('be.visible').type(funder_org)
                    cy.get('#funderResults .list-group-item', { timeout: 10000 }).should('be.visible').contains(funder_org)
                    cy.get('#funderResults .list-group-item').first().click()
                    cy.get('#saveFunderBtn').should('not.be.disabled').click()
                })
            cy.get('#fundersList').should('be.visible').and('contain', funder_org).and('contain', funder_number)
            // Advanced settings section is always open, so we can directly access the field
            // Scroll to the field to ensure it's in view
            cy.get('#id_default_url_subpath').scrollIntoView().should('be.visible')
            cy.get('#id_default_url_subpath').clear().type(default_url_subpath) // provide default_url_subpath
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            verifyAppStatus(app_name_link,  "Running", "Creating", "Running", "Link")

            // wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name_link,  "Running", "Creating", "Running", "Link")
            })

            // check that the default URL subpath was created
            cy.contains('a', app_name_link)
                  .should('have.attr', 'href')
                  .and('include', default_url_subpath)

            // check that the logs page opens for the app
            cy.logf("Now checking that the logs page for the app opens", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_link + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_link + '")').find('a').contains('Logs').click()
            cy.get('h3').should('contain', "Logs")

            // try changing the name, description, etc. of the app and verify it works
            cy.logf("Now changing the name, description, etc of the link app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_link + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_link + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_link) // name should be same as before
            cy.get('#id_name').clear().type(app_name_link_2) // now change name
            cy.get('#id_description').should('have.value', app_description) // description should be same as set before
            cy.get('#id_description').clear().type(app_description_2) // now change description
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_language').should('have.value', 'swe')
            cy.get('#id_language').select('eng')
            // keywords
            cy.get('#div_id_invenio_tags .badge span').should('have.text', keyword)
            cy.get('#div_id_invenio_tags .badge span').should('have.text', keyword).closest('.badge').find('.tag-remove-button').click()
            cy.get('#div_id_invenio_tags').should('be.visible')
                .within(() => {
                    cy.get('input[placeholder*="Start typing"]').should('be.visible').type(keyword_two)
                    cy.get('.dropdown-menu .dropdown-item', { timeout: 10000 }).should('be.visible').first().should('have.text', keyword_two).click()
                })
            // check the previous creators input
            cy.get('#creatorsSortableList').should('be.visible').children('li').should('have.length', 3)
            cy.get('#creatorsSortableList').should('exist').and('be.visible').find('li').eq(1)
                .should('contain', creator_firstname).and('contain', creator_lastname).and('contain', creator_affiliation)
            cy.get('#creatorsSortableList').should('exist').and('be.visible').find('li').eq(2)
                .should('contain', "Jane")
                .and('contain', "Doe")
                .and('contain', "Example Research Institute")
                // Invenio normalizes ORCID identifiers to the ID on storage,
                // so the value is "0000-0002-1584-4316" rather than
                // the full URL the user originally entered.
                .and('contain', "0000-0002-1584-4316")
            cy.get('#creatorsSortableList').children('li').last().find('button[title="Remove creator"]').click()
            // check the previous funder input
            cy.get('#fundersList').should('be.visible').children().should('have.length', 1)
            cy.get('#fundersList').should('be.visible').and('contain', funder_org).and('contain', funder_number)
            cy.get('#addFunderBtn').should('be.visible').click()
            cy.contains('.modal-content', 'Add funder')
                .should('be.visible')
                .within(() => {
                    cy.get('#awardNumberInput').should('be.visible').type(funder_number_two)
                    cy.get('#funderNameInput').should('be.visible').type(funder_org_two)
                    cy.get('#funderResults .list-group-item', { timeout: 10000 }).should('be.visible').contains(funder_org_two)
                    cy.get('#funderResults .list-group-item').first().click()
                    cy.get('#saveFunderBtn').should('not.be.disabled').click()
                })

            cy.get('#id_mount_path').find(':selected').should('contain', mount_path)
            cy.get('#id_port').should('have.value', image_port)
            cy.get('#id_port').clear().type(image_port_2)
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_image').clear().type(image_name_2)
            cy.get('#id_mount_path').select(mount_path_2)
            // Advanced settings section is always open, so we can directly access the field
            // Scroll to the field to ensure it's in view
            cy.get('#id_default_url_subpath').scrollIntoView().should('be.visible')
            cy.get('#id_default_url_subpath').should('have.value', default_url_subpath) // default_url_subpath should be same as before
            cy.get('#id_default_url_subpath').clear().type(changed_default_url_subpath) // provide changed_default_url_subpath
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // NB: it will get status "Running" but it won't work because the new port is incorrect
            verifyAppStatus(app_name_link_2,  "Running", "Changing", "Running", "Link")

            // wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name_link_2,  "Running", "Changing", "Running", "Link")
            })

            // check that the default URL subpath was changed
            cy.contains('a', app_name_link_2)
                  .should('have.attr', 'href')
                  .and('include', changed_default_url_subpath)

            // check that the changes were saved
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_link_2 + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_link_2 + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name_link_2)
            cy.get('#id_description').should('have.value', app_description_2)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_port').should('have.value', image_port_2)
            cy.get('#id_image').should('have.value', image_name_2)
            cy.get('#id_mount_path').find(':selected').should('contain', mount_path_2)
            // The form tag renders the keyword in lowercase.
            cy.get('#div_id_invenio_tags .badge span').should('have.text', keyword_two)
            cy.get('#id_language').should('have.value', 'eng')
            cy.get('#creatorsSortableList').should('be.visible').children('li').should('have.length', 2)
            cy.get('#fundersList').should('be.visible').children().should('have.length', 2)
            cy.get('#fundersList').children().eq(1).find('.fw-semibold')
                .should('contain', funder_org_two)
                .and('contain', funder_number_two)
            // Advanced settings section is always open, so we can directly access the field
            // Scroll to the field to ensure it's in view
            cy.get('#id_default_url_subpath').scrollIntoView().should('be.visible')
            cy.get('#id_default_url_subpath').should('have.value', changed_default_url_subpath) // changed_url_subpath should be same as before

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })


    // TO-DO:
    // Add tests related to integration between Serve and Invenio. This means
    // adding info such as creators, funding, language, etc. to the form and subsequently
    // retrieving this info (from Invenio) when editing the form, making changes
    // again, etc. Then checking if this info is correctly displayed on the public
    // app details public if the app is made public.

    // This test may only work against a Serve instance running on our cluster. as
    // it takes a long time. It does not work on GitHub CI. So it's better
    // to skip it now. As we have Django endpoints, so it can be locally tested directly
    // in the Serve-dev instance.
    // We need to add a test here for validating Site-dir option. See SS-1206 for details
    it("can deploy a shiny app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-custom-example-project", "e2e-deploy-app-test")
        deleteAppIfExists("e2e-custom-example-2-link", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-shiny-example"
        const app_description = "e2e-shiny-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/shiny-adhd-medication-sweden:20240117-062031"
        const image_port = "3838"
        const createResources = Cypress.env('create_resources')
        const app_type = "Shiny App"

        if (createResources === true) {
            // create a Shiny app
            cy.logf("Creating a shiny app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link", shinyAppCmdTimeoutMs)

            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'Running')
            cy.get('tr:contains("' + app_name + '")').find('span').should('contain', 'Link')

            cy.logf("Checking that all shiny app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)
        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // Simple test to create and delete a Dash app
    it("can deploy a dash app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-shiny-example", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-dash-example"
        const app_description = "e2e-dash-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources')
        const app_type = "Dash App"

        if (createResources === true) {
            // create a Dash app
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link")

            // verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // Test creating a Tissuumaps app
    it("can deploy a tissuumaps app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-dash-example", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-tissuumaps-example"
        const app_description = "e2e-tissuumaps-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const createResources = Cypress.env('create_resources')
        const app_type = "TissUUmaps App"

        let volume_display_text = "project-vol (" + project_name + ")"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            cy.logf("Creating a tisuumaps app", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()

            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_volume').select(volume_display_text)
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link")

            // wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name, "Running", "Creating", "Running", "Link")
            })

            cy.logf("Checking that all tissuumaps app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_volume').find(':selected').should('contain', 'project-vol')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // Test creating and deleting a Gradio app
    it("can deploy a gradio app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-tissuumaps-example", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-gradio-example"
        const app_description = "e2e-gradio-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/gradio-flower-classification:20241118-174426"
        const image_port = "7860"
        const createResources = Cypress.env('create_resources')
        const app_type = "Gradio App"

        if (createResources === true) {
            // create a Gradio app
            cy.logf("Creating a gradio app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_mount_path').should('exist')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');

            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link")

            // verify Gradio app values
            cy.logf("Checking that all gradio app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // Test creating and deleting a Streamlit app
    it("can deploy a streamlit app", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-gradio-example", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-streamlit-example"
        const app_description = "e2e-streamlit-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/streamlit-image-to-smiles:20241112-183549"
        const image_port = "8501"
        const createResources = Cypress.env('create_resources')
        const app_type = "Streamlit App"

        if (createResources === true) {
            // create a Streamlit app
            cy.logf("Creating a streamlit app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#id_mount_path').should('exist')
            cy.get('a[href*="settings/?tab=storage"]')
                .should('be.visible')
                .should('contain', 'Manage storage');
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link")

            // verify Streamlit app values
            cy.logf("Checking that all streamlit app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // An advanced test to verify user can modify app settings such as the name and description
    it("can modify app settings resulting in NO k8s redeployment shows correct app status", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-streamlit-example", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-change-app-settings-no-redeploy"
        const app_name_edited = app_name + "-edited"
        const app_description = "e2e-change-app-settings-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources')
        const app_type = "Dash App"

        if (createResources === true) {
            // create a Dash app
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link")

            // verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // edit Dash app: modify the app name and description
            cy.logf("Editing the dash app settings (non redeployment fields)", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()

            // here we change the app name from app_name to app_name_edited
            cy.get('#id_name').type("-edited")
            cy.get('#id_description').type(", edited description.")
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // verify that the app status still equals Running
            verifyAppStatus(app_name_edited,"Running", "Changing", "Running", "Link")

            // wait for 20 seconds and check the app status again
            // this is a brittle part of the test, therefore we wait a longer time to see if the status (incorrectly) changes
            cy.wait(20000).then(() => {
              verifyAppStatus(app_name_edited, "Running", "Changing", "Running", "Link")
            })

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // An advanced test to verify that a user can modify app settings of a Shiny app
    // resulting in k8s redeployment (image) and that it still shows the correct app status.
    // Changed this test to use Shiny rather than Dash because Shiny apps are more
    // complex and need more test coverage.
    // Moreover, testing the scenario that an invalid image input is caught by UI validation
    // and stays on the settings page is already tested by UI e2e tests.
    it("can modify Shiny app settings resulting in k8s redeployment shows correct app status", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-change-app-settings-no-redeploy-edited", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-change-app-settings-redeploy"
        const app_description = "e2e-change-app-settings-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const source_code_url = "https://doi.org/example"
        const image_name_1 = "ghcr.io/alfredeen/hello-shiny:main-20241018-0849"
        const image_name_2 = "ghcr.io/alfredeen/shiny-example:main-20250325-1424"
        const image_port = "3838"
        const subdomain_change = "shiny-app-new-subdomain"
        const createResources = Cypress.env('create_resources')
        const app_type = "Shiny App"

        if (createResources === true) {
            // create a Shiny app
            cy.logf("Creating a shiny app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name_1)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link", shinyAppCmdTimeoutMs)

            // verify Shiny app values
            cy.logf("Checking that all shiny app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_image').should('have.value', image_name_1)
            cy.get('#id_port').should('have.value', image_port)

            // edit Shiny app: modify the app image
            cy.logf("Editing the shiny app settings field Image to a new image", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_image').clear().type(image_name_2)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // verify that the app status now equals Running
            verifyAppStatus(app_name, "Running", "Changing", "Running", "Link", shinyAppCmdTimeoutMs)

            // wait for 30 seconds and check the app status again
            // we want to wait this long to ensure that the status is still correct after the Shiny deployment
            // has rotated the pods
            cy.wait(30000).then(() => {
              verifyAppStatus(app_name, "Running", "Changing", "Running", "Link", shinyAppCmdTimeoutMs)
            })

            // edit Shiny app: change the subdomain
            cy.logf("Editing the shiny app settings field Subdomain", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_subdomain').clear().type(subdomain_change)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // verify that the app status now equals Running
            verifyAppStatus(app_name, "Running", "Changing", "Running", "Link", shinyAppCmdTimeoutMs)

            // wait for 30 seconds and check the app status again
            // we want to wait this long to ensure that the status is still correct after the Shiny deployment
            // has rotated the pods
            cy.wait(30000).then(() => {
              verifyAppStatus(app_name, "Running", "Changing", "Running", "Link", shinyAppCmdTimeoutMs)
            })

            // verify the link app access level is still shown correctly
            cy.logf("Checking that the link shiny app access level is correct", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_access').find(':selected').should('contain', 'Link')

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // A test to verify creating an app and changing the subdomain
    it("can set and change subdomain", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-change-app-settings-redeploy", "e2e-deploy-app-test")

        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-subdomain-change"
        const app_description = "e2e-subdomain-change-description"
        const link_privacy_type_note = "some-text-on-link-only-app"
        const source_code_url = "https://doi.org/example"
        const image_name = "ghcr.io/scilifelabdatacentre/dash-covid-in-sweden:20240117-063059"
        const image_port = "8000"
        const createResources = Cypress.env('create_resources')
        const app_type = "Dash App"
        const subdomain_change = "subdomain-change"

        if (createResources === true) {
            // create a Dash app without custom subdomain
            cy.logf("Creating a dash app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Link')
            cy.get('#id_note_on_linkonly_privacy').type(link_privacy_type_note)
            cy.get('#id_source_code_url').type(source_code_url)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_port').clear().type(image_port)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // check that the app was created
            verifyAppStatus(app_name, "Running", "Creating", "Running", "Link")

            // verify Dash app values
            cy.logf("Checking that all dash app settings were saved", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_name').should('have.value', app_name)
            cy.get('#id_description').should('have.value', app_description)
            cy.get('#id_access').find(':selected').should('contain', 'Link')
            cy.get('#id_image').should('have.value', image_name)
            cy.get('#id_port').should('have.value', image_port)

            // edit Dash app: change the suibdomain to a custom value
            cy.logf("Editing the dash app settings field subdomain", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains('Settings').click()
            cy.get('#id_subdomain').clear().type(subdomain_change)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // back on project page
            cy.url().should("not.include", "/apps/settings")
            cy.get('h3').should('have.text', project_name)

            // verify that the app status now equals Running
            verifyAppStatus(app_name, "Running", "Changing", "Running", "Link")

            // wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
                verifyAppStatus(app_name, "Running", "Changing", "Running", "Link")
              })

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }

    })

    // An advanced test to verify creating apps and changing subdomains. Steps taken:
    // 1. Create app e2e-subdomain-example, subdomain=subdomain-test
    // 2. Attempt create app e2e-second-subdomain-example, using subdomain=subdomain-test
    // 3. Create app e2e-second-subdomain-example, subdomain=subdomain-test2
    // 4. Change the subdomain of the first app to subdomain=subdomain-test3
    it("can set and change custom subdomain several times", { defaultCommandTimeout: defaultCmdTimeoutMs }, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-subdomain-example", "e2e-deploy-app-test")
        deleteAppIfExists("e2e-second-subdomain-example", "e2e-deploy-app-test")

        // names of objects to create
        const project_name = "e2e-deploy-app-test"
        const app_name = "e2e-subdomain-example"
        const app_name_2 = "e2e-second-subdomain-example"
        const app_description = "e2e-subdomain-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const createResources = Cypress.env('create_resources')
        const app_type = "Custom App"
        const subdomain = "subdomain-test"
        const subdomain_2 = "subdomain-test2"
        const subdomain_3 = "subdomain-test3"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // create an app and set a custom subdomain for it
            cy.logf("Now creating an app with a custom subdomain", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            // fill out other fields
            cy.get('#id_name').clear().type(app_name)
            cy.get('#id_description').clear().type(app_description)
            cy.get('#id_port').clear().type("8501")
            cy.get('#id_image').clear().type(image_name)
            cy.get('#id_mount_path').select("/home/data (project-vol (e2e-deploy-app-test))")
            // fill out subdomain field
            cy.get('#id_subdomain').clear().type(subdomain)

            // create the app
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            verifyAppStatus(app_name, "Running", "Creating", "Running", "Project")

            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain)

            // try using the same subdomain the second time
            cy.logf("Now trying to create an app with an already taken subdomain", Cypress.currentTest)
            // cy.get('div.card-body:contains("' + app_type + '")').find('a:contains("Create")').click()
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()

            cy.get('#id_name').clear().type(app_name_2)
            cy.get('#id_description').clear().type(app_description)
            cy.get('#id_port').clear().type("8501")
            cy.get('#id_image').clear().type(image_name)

            // fill out subdomain field
            cy.get('#id_subdomain').clear().type(subdomain)
            cy.get('#id_subdomain').blur()

            cy.get('#div_id_subdomain', {timeout: longCmdTimeoutMs}).should('contain.text', 'The subdomain is not available')

            // instead use a new subdomain
            cy.get('#id_subdomain').clear().type(subdomain_2)
            cy.get('#id_subdomain').blur()
            cy.get('#div_id_subdomain').should('contain.text', 'The subdomain is available')
            // create the app
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            verifyAppStatus(app_name_2, "Running", "Creating", "Running", "Project")

            // check that the app was created with the correct subdomain
            cy.get('a').contains(app_name_2).should('have.attr', 'href').and('include', subdomain_2)

            // change subdomain of a previously created app
            cy.logf("Now changing subdomain of an already created app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a').contains("Settings").click()
            cy.get('#id_subdomain').clear().type(subdomain_3)

            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // check that the app was updated with the correct subdomain
            cy.get('a').contains(app_name).should('have.attr', 'href').and('include', subdomain_3)

            // verify that the app status is not Deleted (Deleting and Created ok)
            cy.get('tr:contains("' + app_name + '")').find('span').should('not.contain', 'Deleted')

            // finally verify status equals Running
            verifyAppStatus(app_name, "Running", "Changing", "Running", "Project")

            // wait for 5 seconds and check the app status again
            cy.wait(5000).then(() => {
              verifyAppStatus(app_name, "Running", "Changing", "Running", "Project")
            })

            // delete the first app
            cy.logf("Deleting the first app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name + '")').find('a.confirm-delete').click()
            cy.get('button').should('be.visible').contains('Delete').click()

            // verify deletion
            // give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name + '")').should('not.exist')
            })

            // delete the second app
            cy.logf("Deleting the second app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_2 + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_2 + '")').find('a.confirm-delete').click()
            cy.get('button').should('be.visible').contains('Delete').click()

            // verify deletion
            // give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_2 + '")').should('not.exist')
            })


        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })

    // This test verifies that the event listener works as expected.
    // This test can be disabled if run in CI.
    it("see correct statuses when deploying apps", {}, () => {

        // delete previous test apps in case the test failed
        cy.logf("Now deleting previous test apps in case the test failed", Cypress.currentTest)
        deleteAppIfExists("e2e-subdomain-example", "e2e-deploy-app-test")
        deleteAppIfExists("e2e-second-subdomain-example", "e2e-deploy-app-test")

        const createResources = Cypress.env('create_resources')
        const project_name = "e2e-deploy-app-test"
        const app_name_statuses = "e2e-app-statuses"
        const app_description = "e2e-subdomain-description"
        const image_name = "ghcr.io/scilifelabdatacentre/example-streamlit:latest"
        const app_type = "Custom App"

        if (createResources === true) {
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()

            // create an app with project permissions
            cy.logf("Now creating an app with a non-existent image reference - expecting Image Error", Cypress.currentTest)
            cy.get('div.card-body:contains("' + app_type + '")').siblings('.card-footer').find('a:contains("Create")').click()
            cy.get('#id_name').type(app_name_statuses)
            cy.get('#id_description').type(app_description)
            cy.get('#id_access').select('Project')
            cy.get('#id_port').type("8501")
            cy.get('#id_image').type("hkqxqxkhkqwxhkxwh") // input random string
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()

            // Invalid image should be rejected by server-side validation - app must not be created
            cy.url().should('include', '/apps/create/')
            cy.contains('Error validating Docker image').should('be.visible')

            // Now submit with a valid image
            cy.logf("Now creating the app with a valid image reference - expecting Running", Cypress.currentTest)
            cy.get('#id_image').clear().type(image_name)
            cy.get('#submit-id-submit').should('be.visible').contains('Submit').click()
            cy.completeAppSubmissionFlow()

            // using longer custom timeout for app to reach Running
            verifyAppStatus(app_name_statuses, "Running", "Creating", "Running", "Project")
            cy.get('tr:contains("' + app_name_statuses + '")', {timeout: longCmdTimeoutMs}).find('span', {timeout: longCmdTimeoutMs}).should('contain', 'Running')

            // delete the app
            cy.logf("Deleting the app", Cypress.currentTest)
            cy.visit("/projects/")
            cy.contains('.card-title', project_name).parents('.card-body').siblings('.card-footer').find('a:contains("Open")').first().click()
            cy.get('tr:contains("' + app_name_statuses + '")').find('i.ellipsis.vertical.icon').click()
            cy.get('tr:contains("' + app_name_statuses + '")').find('a.confirm-delete').click()
            cy.get('button').should('be.visible').contains('Delete').click()

            // verify deletion
            // give the action some time after the click event
            cy.wait(2000).then(() => {
                // verify that the app is not visible in the project overview
                 cy.get('tr:contains("' + app_name_statuses + '")').should('not.exist')
            })

        } else {
            cy.logf('Skipped because create_resources is not true', Cypress.currentTest)
      }
    })


    after(() => {

            if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {

                cy.log("Cleaning up test data via Django endpoint")
                cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA)
                cy.cleanupTestUser(TEST_USER_DATA)
                cy.cleanupTestUser(TEST_SUPERUSER_DATA)
            }

            cy.logf("End after() hook", Cypress.currentTest)
    })

})
