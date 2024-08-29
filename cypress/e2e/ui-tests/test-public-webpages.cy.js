describe("Tests of the public pages of the website", () => {

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)
        cy.visit("/")
        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("should open the home page on link click", () => {
        cy.get("li.nav-item a").contains("Home").click()
        cy.url().should("include", "/home")
    })

    it("should open the Apps page on link click", () => {
        cy.get("li.nav-item a").contains("Apps").click()
        cy.url().should("include", "/apps")
        cy.get('h3').should('contain', 'Public apps')
        cy.get("title").should("have.text", "Apps | SciLifeLab Serve (beta)")

        if (Cypress.env('do_reset_db') === true) {
            // This test was flaky before as other test failures could make this test fail as well
            cy.get('p').should('contain', 'No public apps available.')
        } else {
            cy.get('span.ghost-number').then(($element) => {
                if ($element.length > 0) {
                  // There are public apps and the text must be an integer
                  const text = $element.text().trim();
                  const isInteger = Number.isInteger(Number(text));
                  expect(isInteger).to.be.true;
                }
              });
        }

    })

    it("should open the Models page on link click", () => {
        cy.get("li.nav-item a").contains("Models").click()
        cy.url().should("include", "/models/")
        cy.get('h3').should('contain', 'Model cards')
        cy.get("title").should("have.text", "Models | SciLifeLab Serve (beta)")
        cy.get('p').should('contain', 'No public model cards available.')
    })

    it("should open the User guide page on link click", () => {
        cy.get("li.nav-item a").contains("User guide").click()
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
})
