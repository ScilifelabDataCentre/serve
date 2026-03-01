describe("Tests of the public pages of the website", () => {

    const TEST_USER_DATA = {
    "affiliations": [
        {
            "title": "Uppsala University",
            "ror_id": "https://ror.org/048a87296",
            "department": "test-user-department-name"
        }
    ],
    "email": "test-user@scilifelab.uu.se",
    "first_name": "test-user-first-name",
    "last_name": "test-user-last-name",
    "password": "tesT12345@",
    "username": "e2e-app-metadata-test_user"
};

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

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest)

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {

            cy.log("Populating test data via Django endpoint");
            cy.populateTestUser(TEST_USER_DATA );
            cy.populateTestProject(TEST_USER_DATA , TEST_PROJECT_DATA);
            cy.populateTestApp(TEST_USER_DATA , TEST_PROJECT_DATA, TEST_APP_DATA);
        }
    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)
        cy.visit("/")
        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("should open the home page on link click", () => {
        cy.get(".navbar-brand img").should('have.attr', 'title').should('include','SciLifeLab Serve (beta)')
        cy.get(".navbar-brand").click()
        cy.contains("SciLifeLab Serve (beta)").should("exist")
    })

    it("should open the Apps and models page on link click", () => {
        cy.get("li.nav-item a").contains("Apps & Models").click()
        cy.url().should("include", "/apps")
        cy.get('h3').should('contain', 'Applications & models')
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

    it("should open the Apps & models landing page on link click", () => {

        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {

            cy.get("li.nav-item a").contains("Apps & Models").click()
            cy.url().should("include", "/apps")
            cy.get('h3').should('contain', 'Applications & models')
            cy.get("title").should("have.text", "Apps and models | SciLifeLab Serve (beta)")

            // Find the card with specific app name and owner
            cy.contains('h4.card-title', TEST_APP_DATA.name)
                .parents('.card')
                    .within(() => {
                        // Verify owner information within the same card
                        cy.contains('div.col-12', `${TEST_USER_DATA.first_name} ${TEST_USER_DATA.last_name}`)
                        // Click the Details link
                        cy.get('a[id^="app-metadata"]')
                            .invoke('removeAttr', 'target') // Remove target="_blank"
                                .click()
                    })

            // Verify navigation to details page
            cy.url().should('include', '/records/')

            // Verify app name in header
            cy.get('h2.mb-0').should('contain', TEST_APP_DATA.name)

            // Verify owner information
cy.get('#owner_name').should('contain', `${TEST_USER_DATA.first_name} ${TEST_USER_DATA.last_name}`)
cy.get('#owner_email').should('contain', TEST_USER_DATA.email)
cy.get('#owner_dept').should('contain', TEST_USER_DATA.affiliations[0].department)
cy.get('#owner_aff').should('contain', TEST_USER_DATA.affiliations[0].title)

            // Verify download link exists and has correct href
            cy.contains('a.btn.btn-primary', 'Download all metadata (JSON)')
                .should('have.attr', 'href')
                    .and('include', '/records/')
                        .and('include', '?format=json')

            // Verify the download request completes successfully
            cy.intercept('GET', '**/records/**/*?format=json').as('metadataDownload')
            // Click the download link (opens in same tab)
            cy.contains('a.btn.btn-primary', 'Download all metadata (JSON)')
                .invoke('removeAttr', 'target') // Remove target="_blank"
                    .click()

            // Verify the download request was successful
                cy.wait('@metadataDownload').then((interception) => {
                    expect(interception.response.statusCode).to.eq(200)
                    expect(interception.response.headers['content-type']).to.eq('application/json')
                 })
        }
        else{
            cy.logf("manage_test_data_via_django_endpoint_views is currently disabled. Enable this flag in the cypress.config.js file to run the test.", Cypress.currentTest)
        }
    })

    it("should open the Use in courses page on footer link click", () => {
        // Scroll to footer to make the link visible
        cy.scrollTo('bottom')

        // Click the Use in courses link in the footer
        cy.get('.footer a').contains('Use in courses').click()

        // Verify navigation to Use in courses page
        cy.url().should("include", "/teaching")
        cy.get("title").should("have.text", "Use in courses | SciLifeLab Serve (beta)")

        // Verify page content
        cy.get('h2').should('contain', 'Using SciLifeLab Serve in teaching (courses)')
        cy.get('h3').should('contain', 'Application form')

        // Verify form fields are present
        cy.get('input[name="name"]').should('exist')
        cy.get('input[name="email"]').should('exist')
        cy.get('input[name="course_title"]').should('exist')
        cy.get('input[name="course_dates"]').should('exist')
        cy.get('textarea[name="course_description"]').should('exist')
        cy.get('input[name="captcha"]').should('exist')

        // Verify form labels
        cy.contains('label', 'Your name').should('exist')
        cy.contains('label', 'Your email address').should('exist')
        cy.contains('label', 'Description of course/workshop/webinar').should('exist')

        // Verify submit button
        cy.get('button[type="submit"]').should('contain', 'Submit application')
    })

    it("should validate the Use courses form with invalid input", () => {
        cy.visit("/teaching")
        cy.get("title").should("have.text", "Use in courses | SciLifeLab Serve (beta)")

        // Try to submit empty form
        cy.get('button[type="submit"]').click()

        // Form should show validation errors (HTML5 validation)
        cy.get('input[name="name"]').should('have.attr', 'required')
        cy.get('input[name="email"]').should('have.attr', 'required')
        cy.get('textarea[name="course_description"]').should('have.attr', 'required')

        // Fill in invalid email
        cy.get('input[name="name"]').type('Test User')
        cy.get('input[name="email"]').type('invalid-email')
        cy.get('textarea[name="course_description"]').type('Test description')

        // Try to submit - browser validation should prevent submission
        cy.get('button[type="submit"]').click()

        // Email field should have validation error
        cy.get('input[name="email"]').then(($input) => {
            expect($input[0].validity.valid).to.be.false
        })
    })

    it("should fill the Use in courses form with valid input", () => {
        cy.visit("/teaching")
        cy.get("title").should("have.text", "Use in courses | SciLifeLab Serve (beta)")

        // Fill in all form fields
        cy.get('input[name="name"]').type('John Doe')
        cy.get('input[name="email"]').type('john.doe@example.com')
        cy.get('input[name="course_title"]').type('Introduction to Python')
        cy.get('input[name="course_dates"]').type('2024-01-15 to 2024-01-17')
        cy.get('textarea[name="course_description"]').type('A comprehensive course on Python programming for beginners.')

        // Verify form fields have correct values
        cy.get('input[name="name"]').should('have.value', 'John Doe')
        cy.get('input[name="email"]').should('have.value', 'john.doe@example.com')
        cy.get('input[name="course_title"]').should('have.value', 'Introduction to Python')
        cy.get('input[name="course_dates"]').should('have.value', '2024-01-15 to 2024-01-17')
        cy.get('textarea[name="course_description"]').should('have.value', 'A comprehensive course on Python programming for beginners.')

        // Note: We don't submit the form here because Altcha captcha requires client-side solving
        // which may take time. The form validation and field filling is tested above.
    })

    it("should open the About page on link click, verify content", () => {
        cy.get("li a").contains("About").click()
        cy.url().should("include", "about")
        cy.get("title").should("have.text", "About the platform | SciLifeLab Serve (beta)")
        cy.get('h2').should('contain', 'About the platform')
    })

    it("should open the News page on link click, verify content", () => {
        cy.get("li a").contains("News").click()
        cy.url().should("include", "news")
        cy.get("title").should("have.text", "Platform news | SciLifeLab Serve (beta)")
        cy.get('h2').should('contain', 'Platform news')
    })

    it("should open the Roadmap page on link click, verify content", () => {
        cy.get("li a").contains("Roadmap").click()
        cy.url().should("include", "about/roadmap")
        cy.get("title").should("have.text", "Roadmap | SciLifeLab Serve (beta)")
        cy.get('h2').should('contain', 'Roadmap')
    })

    it("should open the Citing us page on link click, verify content", () => {
        cy.get("li a").contains("Citing us").click()
        cy.url().should("include", "about/cite")
        cy.get("title").should("have.text", "Citing us | SciLifeLab Serve (beta)")
        cy.get('h2').should('contain', 'Citing us')
    })

    it("should open the Privacy policy page on link click, verify content", () => {
        cy.get("li a").contains("Privacy").click()
        cy.url().should("include", "privacy")
        cy.get("title").should("have.text", "Privacy policy | SciLifeLab Serve (beta)")
        cy.get('h2').should('contain', 'Privacy policy')
    })

    it("should open the Contact page on link click, verify content", () => {
        cy.get("li a").contains("Contact").click()
        cy.url().should("include", "contact")
        cy.get("title").should("have.text", "Contact us | SciLifeLab Serve (beta)")
        cy.get('h2').should('contain', 'Contact us')
    })

    after(() => {
        if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {
            cy.log("Cleaning up test data via Django endpoint");
            cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
            cy.cleanupTestUser(TEST_USER_DATA);
        }
        cy.logf("End after() hook", Cypress.currentTest)
    })
})
