describe("Tests of the app details pages (mock records)", () => {

    before(() => {
        cy.logf("Begin before() hook", Cypress.currentTest)

    })

    beforeEach(() => {
        cy.logf("Begin beforeEach() hook", Cypress.currentTest)
        cy.visit("/")
        cy.logf("End beforeEach() hook", Cypress.currentTest)
    })

    it("should open the app details page for the mock record", () => {
        const title = "Mock App Title"
        const doi = "https://doi.org/10.83812/scilifelab.rrrrr-rrrrr"

        cy.visit("/records/mock-record-id/")
        cy.get("title").should("have.text", "Mock App Title | SciLifeLab Serve (beta)")

        // check title block
        cy.get('.d-flex.flex-column.flex-md-row').first()
        .within(() => {
            cy.get('h2').should('have.text', title)
            cy.get('p').should('contain', "Version 2").and('contain', "latest version")
        })
        cy.get('.d-flex.flex-column.flex-md-row').first()
        .within(() => {
            cy.contains('a', 'Run Locally').should('have.attr', 'data-app-name', title)

            cy.contains('a', 'Launch (new tab)').should('have.attr', 'href', 'https://mock-app.serve.scilifelab.se')
        })

        // check record description block
        cy.contains('.card', 'Record description').within(() => {
            cy.contains('dt', 'Title').next('dd').should('contain', title)
            cy.contains('dt', 'DOI').next('dd').should('contain', doi)
            cy.contains('dt', 'Description').next('dd').should('contain', "Mock description of the app.")
            cy.contains('dt', 'URL').next('dd').should('contain', "https://mock-app.serve.scilifelab.se")
            cy.contains('dt', 'Source code').next('dd').should('contain', "https://github.com/some/repo")
            cy.contains('dt', 'Docker image').next('dd').should('contain', "ghcr.io/scilifelabdatacentre/example-dash:240314-1126")
            cy.contains('dt', 'Language').next('dd').should('contain', "English")
            cy.contains('dt', 'Date submitted').next('dd').should('contain', '2024-01-01 11:00')
            cy.contains('dt', 'Date updated').next('dd').should('contain', '2024-01-02 13:00')
            cy.contains('dt', 'Date available').next('dd').should('contain', '2024-01-03 15:00')
            cy.contains('.tag-name', 'Genes, pX').should('be.visible')
            cy.contains('.tag-name', 'Antigens').should('be.visible')
            cy.contains('dt', 'Funding')
                .next('dd')
                .should('contain', 'Knut and Alice Wallenberg Foundation')
                .and('contain', 'award 1')

            })

        // creators block
        cy.contains('.card', 'Creators').within(() => {
            cy.contains('.card-username', 'Doe, Jane').should('be.visible')
            cy.contains('.card-username', 'Doe, John')
                .should('be.visible')
                .and('have.attr', 'href', 'https://orcid.org/0000-0001-5393-1421')
            })

        // versions block
        cy.contains('.card', 'Versions').within(() => {
        cy.contains('Version 2:').should('be.visible')
        cy.contains(doi).should('be.visible')
        cy.contains('.badge', 'current').should('be.visible')
        cy.contains('Version 1:').should('be.visible')
        cy.contains('a', 'https://doi.org/10.83812/scilifelab.rrrr2-rrrr2')
            .should('have.attr', 'href', '/records/rrrr2-rrrr2/')
        cy.contains('https://doi.org/10.83812/scilifelab.ppppp-ppppp')
            .should('be.visible')
        })

        // citation block
        cy.contains('.card', 'Citation').within(() => {
        cy.contains('a', 'Citeproc JSON')
            .should('have.attr', 'href', `https://api.datacite.org/application/vnd.citationstyles.csl+json/10.83812/scilifelab.rrrrr-rrrrr`)
        cy.contains('a', 'BibTeX')
            .should('have.attr', 'href', `https://api.datacite.org/application/x-bibtex/10.83812/scilifelab.rrrrr-rrrrr`)
        cy.contains('a', 'RIS')
            .should('have.attr', 'href', `https://api.datacite.org/application/x-research-info-systems/10.83812/scilifelab.rrrrr-rrrrr`)
        })

        // metadata export block
        cy.contains('.card', 'Metadata export').within(() => {
        cy.contains('a', 'XML format').should('have.attr', 'href')
        cy.contains('a', 'JSON format').should('have.attr', 'href')
        cy.contains('a', 'Schema.org JSON-LD').should('have.attr', 'href')
        })

    })

    it("should open the tombstone page for the mock tombstone record", () => {
        cy.visit("/records/mock-deleted-record-id/")
        cy.get("title").should("have.text", "Record deleted | SciLifeLab Serve (beta)")
        cy.get('.container-fluid.pb-3').within(() => {

        cy.get('h2').first().should('have.text', 'Record deleted')
        cy.contains('The record you are trying to access was removed').should('be.visible')
        cy.contains('dt', 'Date of removal:').next('dd').should('have.text', "2024-01-01")
        cy.contains('dt', 'Reason for removal:').next('dd').should('have.text', "Personal data issue")
        cy.contains('dt', 'Removal note:').next('dd').should('have.text', "Some reason for removal here")
        cy.contains('dt', 'Record DOI:').next('dd').should('have.text', "https://doi.org/10.83812/scilifelab.ddddd-ddddd")
        })

    })

})
