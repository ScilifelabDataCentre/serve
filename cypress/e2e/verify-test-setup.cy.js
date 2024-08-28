describe("Simple tests to verify the test framework setup", () => {

  before(() => {
    // runs once before all tests in the block
    cy.logf("Start before() hook.", Cypress.currentTest)

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
