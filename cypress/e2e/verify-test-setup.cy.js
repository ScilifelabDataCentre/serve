describe("Simple tests to verify the test framework setup", () => {

  before(() => {
    // runs once before all tests in the block
    cy.log("Start before() hook", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
    expect(Cypress.currentTest.titlePath[0]).to.eq('Simple tests to verify the test framework setup')
    expect(Cypress.currentTest.title).to.be.a('string')
    cy.log("End before() hook", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
  })

  beforeEach(() => {
    // runs before each test in the block
    cy.log("Start beforeEach() hook", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
    expect(Cypress.currentTest.titlePath[0]).to.eq('Simple tests to verify the test framework setup')
    cy.log("End beforeEach() hook", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
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

  it("can access and parse the test fixtures", () => {
    expect(Cypress.currentTest.titlePath[1]).to.eq('can access and parse the test fixtures')

    cy.fixture('users.json').then(function (data) {
      cy.log(data.login_user.username, `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
      cy.log(data.contributor.username, `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
      cy.log(data.contributor.email, `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
    })
  })

})
