describe("Test of the public apps page", () => {

    beforeEach(() => {

        cy.visit("/apps")
    })

    it("should contain header with text Apps", () => {

        cy.get('h3').should('contain', 'apps')
        cy.get("title").should("have.text", "Apps | SciLifeLab Serve (beta)")
    })

})
