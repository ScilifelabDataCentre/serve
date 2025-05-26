describe("Tests of the public pages of the website", () => {

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)
        cy.visit("/")
        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("should open the home page on link click", () => {
        cy.get("li.nav-item a").contains("Home").click()
        cy.contains("SciLifeLab Serve").should("exist")
    })

    it("should open the Apps and models page on link click", () => {
        cy.get("li.nav-item a").contains("Apps & Models").click()
        cy.url().should("include", "/apps")
        cy.get('h3').should('contain', 'Public Applications & Models')
        cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")

        if (Cypress.env('do_reset_db') === true) {
            // This test was flaky before as other test failures could make this test fail as well
            cy.get('p').should('contain', 'No public apps available.')
        } else {
            cy.get('h3').then($parent => {
                if ($parent.find("span.ghost-number").length > 0) {
                    cy.get('span.ghost-number').then(($element) => {
                        // There are public apps and the text must be an integer
                        const text = $element.text().trim();
                        const isInteger = Number.isInteger(Number(text));
                        expect(isInteger).to.be.true;
                    });
                }
            });
        }
    })

    it("should open the User guide page on link click", () => {
        cy.get("li.nav-item a").contains("User Guide").click()
        cy.url().should("include", "/docs/")
        cy.get('[data-cy="sidebar-title"]').should('contain', 'user guide') // check that the sidebar title is there, comes from our templates
    })

    it("should open the signup page on link click", () => {
        cy.get("li.nav-item a").contains("Register").click()
        cy.url().should("include", "signup")
    })

    it("should open the login page on link click", () => {
        cy.get("li.nav-item a").contains("Log in").click()
        cy.url().should("include", "accounts/login")
    })

    it("should have proper title", () => {
	    cy.get("title").should("have.text", "Home | SciLifeLab Serve (beta)")
    })

    it("should open the App landing page on link click", () => {
        //data to create a test app
        const TEST_USER = {
            "affiliation": "uu",
            "department": "test-user-department-name",
            "email": "test-user@scilifelab.uu.se",
            "first_name": "test-user-first-name",
            "last_name": "test-user-last-name",
            "password": "tesT12345@",
            "username": "e2e-app-metadata-test_user"
        }

        const TEST_PROJECT_DATA = {
        project_name: "e2e-app-metadata-test-proj",
        project_description: "e2e-app-metadata-test-proj-desc",
        };

        const TEST_APP_DATA = {
                app_slug: "dashapp",
                name: "e2e-app-metadata-test-app-name",
                description: "e2e-app-metadata-test-app-description",
                access: "public",
                port: 8000,
                image: "ghcr.io/scilifelabdatacentre/example-dash:latest",
                source_code_url: "https://someurlthatdoesnotexist.com"
              };

        cy.log("Populating test data via Django endpoint");
        cy.populateTestUser(TEST_USER );
        cy.populateTestProject(TEST_USER , TEST_PROJECT_DATA);
        cy.populateTestApp(TEST_USER , TEST_PROJECT_DATA, TEST_APP_DATA);

        cy.get("li.nav-item a").contains("Apps & Models").click()
        cy.url().should("include", "/apps")
        cy.get('h3').should('contain', 'Public Applications & Models')
        cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")

        // Find the card with specific app name and owner
        cy.contains('h5.card-title', TEST_APP_DATA.name)
            .parents('.card')
            .within(() => {
                // Verify owner information within the same card
                cy.contains('div.col-12', `Owner: ${TEST_USER.first_name} ${TEST_USER.last_name}`)
                // Click the Details link
                cy.get('a#app-metadata')
                    .invoke('removeAttr', 'target') // Remove target="_blank"
                        .click()
            })

        // Verify navigation to details page
        cy.url().should('include', '/metadata/dashapp/')

        // Verify app name in header
        cy.get('h2.mb-0').should('contain', TEST_APP_DATA.name)

        // Verify owner information
        cy.get('#owner_name').should('contain', `${TEST_USER.first_name} ${TEST_USER.last_name}`)
        cy.get('#owner_email').should('contain', TEST_USER.email)
        cy.get('#owner_dept').should('contain', TEST_USER.department)
        cy.get('#owner_aff').should('contain', 'Uppsala universitet (Uppsala University)')

        // Verify download link exists and has correct href
        cy.contains('a.btn-lg', 'Download All Metadata (JSON)')
            .should('have.attr', 'href')
            .and('include', '/apps/metadata/')
            .and('include', '?format=json')

        // Verify the download request completes successfully
        cy.intercept('GET', '**/metadata/**/*?format=json').as('metadataDownload')

        // Click the download link (opens in same tab)
        cy.contains('a.btn-lg', 'Download All Metadata (JSON)')
            .invoke('removeAttr', 'target') // Remove target="_blank"
                .click()

        // Verify the download request was successful
            cy.wait('@metadataDownload').then((interception) => {
                expect(interception.response.statusCode).to.eq(200)
                expect(interception.response.headers['content-type']).to.eq('application/json')
        })

        cy.log("Cleaning up test data via Django endpoint");
        cy.cleanupTestProject(TEST_USER, TEST_PROJECT_DATA);
        cy.cleanupTestUser(TEST_USER);
    })
})
