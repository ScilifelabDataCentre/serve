describe("Simple tests to verify the test framework setup", () => {

  // Cypress env settings
  let env_do_reset_db
  let env_wait_db_reset
  let env_create_resources
  let env_run_extended_k8s_checks
  let env_non_existent_setting

  before(() => {
    // runs once before all tests in the block
    cy.logf("Start before() hook.", Cypress.currentTest)

    env_do_reset_db = Cypress.env('do_reset_db') ?? "unset"
    env_wait_db_reset = Cypress.env('wait_db_reset') ?? "unset"
    env_create_resources = Cypress.env('create_resources') ?? "unset"
    env_run_extended_k8s_checks = Cypress.env('run_extended_k8s_checks') ?? "unset"
    env_non_existent_setting = Cypress.env('non_existent_setting') ?? true

    //cy.log("Start before() hook", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
    expect(Cypress.currentTest.titlePath[0]).to.eq('Simple tests to verify the test framework setup')
    expect(Cypress.currentTest.title).to.be.a('string')
    cy.logf("End before() hook.", Cypress.currentTest)
  })

  beforeEach(() => {
    // runs before each test in the block
    cy.logf("Start beforeEach() hook", Cypress.currentTest)
    expect(Cypress.currentTest.titlePath[0]).to.eq('Simple tests to verify the test framework setup')
    cy.logf("End beforeEach() hook", Cypress.currentTest)
  })

  it("passes", () => {
  })

  it("verify current test title", () => {
    expect(Cypress.currentTest.titlePath[1]).to.eq('verify current test title')
  })

  it("verify Cypress env settings", () => {
    cy.logf("wait_db_reset:" + env_wait_db_reset, Cypress.currentTest)
    expect(env_wait_db_reset > 0)

    cy.logf("non_existent_setting:" + env_non_existent_setting, Cypress.currentTest)
    expect(env_non_existent_setting === true)
  })

  it("display all Cypress env settings", () => {
    cy.logf("do_reset_db:" + env_do_reset_db, Cypress.currentTest)
    cy.logf("wait_db_reset:" + env_wait_db_reset, Cypress.currentTest)
    cy.logf("create_resources:" + env_create_resources, Cypress.currentTest)
    cy.logf("run_extended_k8s_checks:" + env_run_extended_k8s_checks, Cypress.currentTest)
  })

  it("cypress can log to the terminal", () => {
    expect(Cypress.currentTest.titlePath[1]).to.eq('cypress can log to the terminal')
    cy.log("Verify that this message is output to the terminal.", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
  })

  it("cypress can log to the terminal using custom command logf", () => {
    expect(Cypress.currentTest.titlePath[1]).to.eq('cypress can log to the terminal using custom command logf')
    cy.logf("Verify that this message is output to the terminal.", Cypress.currentTest)
    cy.logf("Verify that this message with args [a, b] is output to the terminal.", Cypress.currentTest, ["a", "b"])
  })

  it("can access and parse the test fixtures", () => {
    expect(Cypress.currentTest.titlePath[1]).to.eq('can access and parse the test fixtures')

    cy.fixture('users.json').then(function (data) {
      cy.logf(data.login_user.username, Cypress.currentTest)
      cy.logf(data.contributor.username, Cypress.currentTest)
      cy.logf(data.contributor.email, Cypress.currentTest)
    })
  })

})
