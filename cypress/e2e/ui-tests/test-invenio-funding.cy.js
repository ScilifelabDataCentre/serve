if (Cypress.env("create_resources") === true) {
    describe.skip("Test Invenio funding fields in app forms", () => {
        let users;
        let TEST_USER_DATA;
        const TEST_PROJECT_DATA = {
            project_name: "e2e-invenio-funding-test-proj",
            project_description: "Project for testing funding form behavior",
        };

        const APP_SLUGS = ["customapp", "dashapp", "gradio", "shinyapp", "streamlit"];

        const openProjectOverview = () => {
            cy.visit("/projects/");
            cy.contains(".card-title", TEST_PROJECT_DATA.project_name)
                .parents(".card-body")
                .siblings(".card-footer")
                .find('a:contains("Open")')
                .first()
                .click();
        };

        const openCreateForm = (slug) => {
            openProjectOverview();
            cy.get(`a[href*="/apps/create/${slug}"]`).first().should("be.visible").click();
        };

        const addFundingEntry = ({ query, number, title, url = "" }) => {
            cy.get("#addFunderBtn").should("be.visible").click();
            cy.get("#funderModal").should("be.visible");

            cy.get("#funderNameInput").clear().type(query, { delay: 20 });
            cy.wait("@funders");
            cy.get("#funderResults [data-idx='0']", { timeout: 15000 }).should("exist").click({ force: true });

            cy.get("#awardNumberInput").clear().type(number);
            cy.get("#awardTitleInput").clear().type(title);
            cy.get("#awardUrlInput").clear().then(($input) => {
                if (url) {
                    cy.wrap($input).type(url);
                }
            });

            cy.get("#saveFunderBtn").should("not.be.disabled").click();
            cy.get("#funderModal").should("not.be.visible");
        };

        before(function () {
            cy.logf("Begin before() hook", Cypress.currentTest);

            if (Cypress.env("manage_test_data_via_django_endpoint_views") !== true) {
                cy.log("Skipping test: requires manage_test_data_via_django_endpoint_views=true");
                this.skip();
            }

            cy.log("Populating test data via Django endpoint");
            cy.fixture("users.json").then((data) => {
                users = data;
                TEST_USER_DATA = data.invenio_user;
                cy.populateTestUser(TEST_USER_DATA);
                cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                cy.populateTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
            });

            cy.logf("End before() hook", Cypress.currentTest);
        });

        beforeEach(() => {
            cy.logf("Begin beforeEach() hook", Cypress.currentTest);
            cy.fixture("users.json").then((data) => {
                users = data;
                cy.loginViaUI(users.invenio_user.email, users.invenio_user.password);
            });
            cy.intercept("GET", "**/api/invenio/funders/**", {
                statusCode: 200,
                fixture: "invenio-funders.json",
            }).as("funders");
            cy.logf("End beforeEach() hook", Cypress.currentTest);
        });

        it("shows funding field on all targeted create forms", () => {
            APP_SLUGS.forEach((slug) => {
                openCreateForm(slug);
                cy.get("#id_funding_sources_json").should("exist").and("have.value", "[]");
                cy.get("#addFunderBtn").should("be.visible");
            });
        });

        it("custom app autocomplete and edit modal keep funder and award fields", () => {
            openCreateForm("customapp");

            addFundingEntry({
                query: "Uppsal",
                number: "2024-01567",
                title: "Uppsala Precision Medicine Grant",
            });

            cy.get("#fundersList").should("contain", "2024-01567");

            cy.get("#id_funding_sources_json")
                .invoke("val")
                .then((raw) => {
                    const funding = JSON.parse(raw);
                    expect(funding).to.have.length(1);
                    expect(funding[0].funder_id).to.be.a("string").and.not.be.empty;
                    expect(funding[0].funder_name).to.be.a("string").and.not.be.empty;
                    expect(funding[0].number).to.equal("2024-01567");
                    expect(funding[0].title).to.equal("Uppsala Precision Medicine Grant");
                    expect(funding[0].url).to.equal("");
                    cy.wrap(funding[0].funder_name).as("selectedFunderName");
                });

            cy.get("#fundersList [data-edit='0']").click();
            cy.get("#funderModal").should("be.visible");
            cy.get("#funderModalLabel").should("contain", "Edit funder");
            cy.get("@selectedFunderName").then((selectedFunderName) => {
                cy.get("#funderNameInput").should("have.value", selectedFunderName);
            });
            cy.get("#awardNumberInput").should("have.value", "2024-01567");
            cy.get("#awardTitleInput").should("have.value", "Uppsala Precision Medicine Grant");
            cy.get("#awardUrlInput").should("have.value", "");
        });

        after(() => {
            cy.logf("Begin after() hook", Cypress.currentTest);

            if (Cypress.env("manage_test_data_via_django_endpoint_views") === true) {
                cy.log("Cleaning up test data via Django endpoint");
                cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                cy.cleanupTestUser(TEST_USER_DATA);
            }

            cy.logf("End after() hook", Cypress.currentTest);
        });
    });
}
