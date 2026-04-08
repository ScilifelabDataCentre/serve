Write commit subjects in the style already used in this repository.

Preferred formats:
- `<type>: <short imperative summary>`
- `<JIRA-KEY> <type>: <short imperative summary>` when there is a related ticket and you want the commit to match the PR/squash style

Use Conventional Commit types such as `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, or `ci`.

Guidelines:
- Keep the subject concise and specific
- Use imperative mood (`add`, `fix`, `update`), not past tense
- Do not end the subject with a period
- Avoid vague summaries like `misc updates` or `fix stuff`

Examples:
- `feat: improve task success counting for validation failures`
- `fix: correct OpenAPI content stats URL`
- `SS-1830 feat: refactor app submission flow to rely on background tasks`
