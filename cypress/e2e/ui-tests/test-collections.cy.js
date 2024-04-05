describe("Test collections functionality", () => {

    // Tests performed as an authenticated user that has superuser privileges because that's the one that can currently create collections
    // user: no-reply-collections-user@scilifelab.se"

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
        cy.log("Running seed_collections_user.py")
        cy.exec("./cypress/e2e/db-seed-collections-user.sh")
    })

    it("can create a new collection through the django admin interface, can subsequently see this collection page", () => {

        const collection_name = "test-collection"
        const collection_description = "test-collection-description"
        const collection_website = "https://collection.com"
        const collection_slug = "test-collection"
        const collection_zenodo_id = "opensci-scilifelab-dc"
        const collection_app_name = "collection-app-name" // created in the seed_collections_user.py
        const collection_project_name = "e2e-collections-test-proj" // created in the seed_collections_user.py

        cy.log("Creating a collection")
        // log in as admin
        cy.visit("/admin/")
        cy.get('#id_username').type('no-reply-collections-user@scilifelab.se')
        cy.get('#id_password').type('tesT12345@')
        cy.get('input').contains('Log in').click()

        // create a collection
        cy.get('tr.model-collection').find('a.addlink').click()
        cy.get('#id_maintainer').select('no-reply-collections-user@scilifelab.se')
        cy.get('#id_name').type(collection_name)
        cy.get('#id_description').type(collection_description)
        cy.get('#id_website').type(collection_website)
        cy.get('#id_slug').type(collection_slug)
        cy.get('#id_zenodo_community_id').type(collection_zenodo_id)
        cy.get('input[name=_save]').click()
        cy.get('li.success').should('contain', "was added successfully") // confirm collection was created

        cy.log("Adding an app to the collection")
        cy.get('tr.model-appinstance').find('a').first().click()
        cy.get('tr').find('a').contains(collection_app_name).click()
        cy.get('#id_collections').select(collection_name)
        cy.get('input[name=_save]').click()
        cy.get('li.success').should('contain', "was changed successfully") // confirm app name has been added to the collection

        cy.log("Can see the created collection page")
        cy.visit("/collections/" + collection_slug)
        cy.get('h3').should('contain', collection_name)
        cy.get('#collection-description').should('contain', collection_description)
        cy.get('a#collection-website').should('have.attr', 'href', collection_website)

        // check that the app that was added to the collection is displayed
        cy.get('h4#apps').should("exist")
        cy.get('h5.card-title').contains(collection_app_name).should('exist')

        // check that datasets entry fetching worked
        cy.get('h4#datasets').should("exist")
        cy.get('div#zenodo-entries').should('not.contain', "Fetching Zenodo entries failed")

        cy.log("Cleaning up afterwards - removing the project and app")
        cy.visit("/projects/")
        cy.contains('.card-title', collection_project_name).parents('.card-body').siblings('.card-footer').find('.confirm-delete').click()
            .then((href) => {
                cy.get("h1#modalConfirmDeleteLabel").then(function($elem) {
                    cy.get('div#modalConfirmDeleteFooter').find('button').contains('Delete').click()
                    cy.contains(collection_project_name).should('not.exist') // confirm the project has been deleted
               })
            })
    })

})
