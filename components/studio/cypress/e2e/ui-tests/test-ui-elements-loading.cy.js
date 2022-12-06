describe("test load of UI elements", () => {
    beforeEach(() => {
        cy.visit("http://studio.127.0.0.1.nip.io:8080")
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
    it ("Test load teaching page via ui", () => {
        cy.get(".sidebar-link").get("a[href*='/teaching/']").click();
        cy.url().should("include", "teaching");
	cy.get('.h1').should("have.text", "Teaching through SciLifeLab Serve");
    })
    it ("Test load about page via ui", () => {
        cy.get(".sidebar-link").get("a[href*='/about/']").contains("About").click();
        cy.url().should("include", "about");
	cy.get('.h1').should("have.text", "About SciLifeLab Serve");
    })
})

describe('test load of about page ui elements', () => {
  beforeEach(() => {
    cy.visit("http://studio.127.0.0.1.nip.io:8080/about/")
  })
  it('Test load first scilife image', () => {
    cy.get("img").each((item, index, list) => {
      cy.wrap(item).should("be.visible")
      .and(($img) => {
        expect($img[0].naturalWidth).to.be.greaterThan(0)
      })
    })
  })
})
