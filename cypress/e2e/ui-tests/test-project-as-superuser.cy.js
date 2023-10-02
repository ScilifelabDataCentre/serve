describe("Test superuser access", () => {

    // Tests performed as an authenticated user that has superuser privileges
    // user: admin

    let users

    before(() => {
        // seed the db with: contributor user, a blank project
        cy.log("Seeding the db for the superuser tests. Running db-seed-contributor.sh");
        cy.exec("./cypress/e2e/db-reset.sh")
        cy.wait(60000)
        cy.visit("/")
        cy.log("Running seed_superuser.py")
        cy.exec("./cypress/e2e/db-seed-superuser.sh")
    })

    beforeEach(() => {
        // username in fixture must match username in db-reset.sh
        cy.log("Logging in as superuser")
        cy.fixture('users.json').then(function (data) {
            users = data

            cy.loginViaApi(users.superuser.username, users.superuser.password)
        })
    })

    it.skip("can see extra deployment options and extra settings in a project", () => {
    })

    it.skip("can bypass N project limit", () => {
    })

    it.skip("can bypass N apps limit", () => {
    })

})
