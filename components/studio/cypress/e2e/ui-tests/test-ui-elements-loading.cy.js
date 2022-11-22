describe("test load of UI elements", () => {
    beforeEach(() => {
        cy.visit("https://nikita.serve-dev.scilifelab.se")
    })

    it ("Test main page load", () => {
        cy.get('.h1').should('have.text', 'SciLifeLab Serve');
    })
    it ("Test load contact page via ui", () => {
        cy.get(".sidebar-link").get("a[href*='/contact/']").click();
        cy.url().should("include", "contact")
    })
    it ("Test load user guide page via ui", () => {
        cy.get(".sidebar-link").contains("User Guide").click();
        cy.get("ul[id*='submenu1'] > li").should(($lis) => {
            expect($lis).to.have.length(6)
        })
    })
})