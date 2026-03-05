if (Cypress.env("create_resources") === true) {
    describe("Test Invenio funding fields in app forms", () => {
        const defaultCmdTimeoutMs = 10000;
        let users;
        let TEST_USER_DATA;
        const getEndpointUserData = (userData) => ({
            ...userData,
            // Keep endpoint-created user aligned with environments that use email as username.
            username: userData.email
        });

        const TEST_PROJECT_DATA = {
            project_name: "e2e-invenio-funding-test-proj",
            project_description: "Project for testing funding form behavior"
        };

        const appSlugs = ["customapp", "dashapp", "gradio", "shinyapp", "streamlit"];

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

            cy.get("#funderNameInput").clear().type(query);
            cy.get("#funderResults [data-idx='0']", { timeout: 10000 })
                .should("be.visible")
                .click();

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

        const getFormField = (requestBody, key) => {
            if (typeof requestBody === "string") {
                return new URLSearchParams(requestBody).get(key);
            }
            if (requestBody && typeof requestBody === "object") {
                return requestBody[key] || null;
            }
            return null;
        };

        before({ defaultCommandTimeout: defaultCmdTimeoutMs }, () => {
            cy.logf("Begin before() hook", Cypress.currentTest);

            if (Cypress.env("manage_test_data_via_django_endpoint_views") === true) {
                cy.log("Populating test data via Django endpoint");
                cy.fixture("users.json").then((data) => {
                    TEST_USER_DATA = getEndpointUserData(data.deploy_app_user);
                    cy.populateTestUser(TEST_USER_DATA);
                    cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                    cy.populateTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                });
            } else {
                if (Cypress.env("do_reset_db") === true) {
                    cy.logf("Resetting db state. Running db-reset.sh", Cypress.currentTest);
                    cy.exec("./cypress/e2e/db-reset.sh");
                    cy.wait(Cypress.env("wait_db_reset"));
                } else {
                    cy.logf("Skipping resetting the db state.", Cypress.currentTest);
                }

                cy.visit("/", {
                    timeout: 45000,
                    retryOnStatusCodeFailure: true,
                    retryOnNetworkFailure: true
                });

                cy.logf("Running seed-deploy-app-user.py", Cypress.currentTest);
                cy.exec("./cypress/e2e/db-seed-deploy-app-user.sh");
            }

            cy.fixture("users.json").then((data) => {
                users = data;
                cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password);
            });

            cy.logf("End before() hook", Cypress.currentTest);
        });

        beforeEach(() => {
            cy.logf("Begin beforeEach() hook", Cypress.currentTest);
            cy.fixture("users.json").then((data) => {
                users = data;
                cy.loginViaApi(users.deploy_app_user.email, users.deploy_app_user.password);
            });
            cy.intercept(
                {
                    method: "GET",
                    pathname: "/api/invenio/funders/",
                    query: {
                        q: /.+/
                    }
                },
                { statusCode: 200, fixture: "invenio-funders.json" }
            ).as("funders");
            cy.logf("End beforeEach() hook", Cypress.currentTest);
        });

        it("shows funding field on all targeted create forms", () => {
            appSlugs.forEach((slug) => {
                openCreateForm(slug);

                cy.get("#id_funding_sources_json").should("exist").and("have.value", "[]");
                cy.get("#addFunderBtn").should("be.visible");
            });
        });

        it("custom app autocomplete and edit modal keep funder and award fields", () => {
            openCreateForm("customapp");

            addFundingEntry({
                query: "Uppsala",
                number: "2024-01567",
                title: "Uppsala Precision Medicine Grant"
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

        it("custom app submit sends funding_sources_json payload", () => {
            openCreateForm("customapp");

            const appName = `e2e-funding-submit-${Date.now()}`;
            cy.intercept("POST", "**/apps/create/customapp*").as("createCustomApp");

            cy.get("#id_name").type(appName);
            cy.get("#id_description").type("App created by funding Cypress test");
            cy.get("#id_access").select("Public");
            cy.get("#id_source_code_url").clear().type("https://example.org/source");
            cy.get("#id_port").clear().type("8501");
            cy.get("#id_image").clear().type("ghcr.io/scilifelabdatacentre/example-streamlit:latest");

            cy.get("body").then(($body) => {
                if ($body.find("#id_mount_path").length) {
                    cy.get("#id_mount_path option").then(($options) => {
                        const firstUsable = [...$options].find((opt) => !!opt.value);
                        if (firstUsable) {
                            cy.get("#id_mount_path").select(firstUsable.value);
                        }
                    });
                }
            });

            addFundingEntry({
                query: "Uppsala",
                number: "2024-01567",
                title: "Uppsala Precision Medicine Grant"
            });

            cy.get("#submit-id-submit").should("be.visible").contains("Submit").click();

            cy.wait("@createCustomApp").then((interception) => {
                const fundingRaw = getFormField(interception.request.body, "funding_sources_json");
                expect(fundingRaw, "funding_sources_json in submit payload").to.be.a("string").and.not.be.empty;

                const funding = JSON.parse(fundingRaw);
                expect(funding).to.have.length(1);
                expect(funding[0].funder_id).to.be.a("string").and.not.be.empty;
                expect(funding[0].funder_name).to.be.a("string").and.not.be.empty;
                expect(funding[0].number).to.equal("2024-01567");
                expect(funding[0].title).to.equal("Uppsala Precision Medicine Grant");
                expect(funding[0].url).to.equal("");
            });
        });

        after(() => {

            if (Cypress.env('manage_test_data_via_django_endpoint_views') === true) {

                cy.log("Cleaning up test data via Django endpoint");
                cy.cleanupTestProject(TEST_USER_DATA, TEST_PROJECT_DATA);
                cy.cleanupTestUser(TEST_USER_DATA);
            }

            cy.logf("End after() hook", Cypress.currentTest)
        });
    });
}
