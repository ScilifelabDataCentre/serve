describe("Simple tests to verify the test framework setup", () => {

  before(() => {
    // runs once before all tests in the block
    cy.log("before() hook", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
})

  beforeEach(() => {
    // runs before each test in the block
    cy.log("beforeEach() hook", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
  })

  it("passes", () => {
  })

  it("cypress can log to the terminal", () => {
    cy.log("Verify that this message is output to the terminal.", `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
  })

  it("can access and parse the test fixtures", () => {
    cy.fixture('users.json').then(function (data) {
      cy.log(data.login_user.username, `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
      cy.log(data.contributor.username, `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
      cy.log(data.contributor.email, `(TEST: ${Cypress.currentTest.title}, ${new Date().getTime()})`)
    })
  })

})
