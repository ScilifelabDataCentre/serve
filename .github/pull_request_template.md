## Description

> Describe your changes here to communicate to the maintainers why we should accept this pull request.
> If it fixes a bug or resolves a feature request, be sure to include a link to that issue.

## Checklist

> If you're unsure about any of the items below, don't hesitate to ask. We're here to help!
> This is simply a reminder of what we are going to look for before merging your code.

- [ ] This pull request is against **develop** branch (not applicable for hotfixes)
- [ ] I have included a link to the issue on GitHub or JIRA (if any)
- [ ] I have included migration files (if there are changes to the model classes)
- [ ] I have added or updated unit and end2end tests to complement my changes
- [ ] I have ran unit and end2end tests
- [ ] I have updated the related documentation (if necessary)
- [ ] I have added a reviewer for this pull request
- [ ] I have added myself as an author for this pull request
- [ ] In the case I have modified settings.py, then I have also updated the studio-settings-configmap.yaml file in serve-charts
- [ ] In case your changes are large enough, did you deploy your changes to develop instance?

# PR cheatsheet

- PR -- pull request
- Include jira ticket in the PR title (like `SS-1234 Introduced machine learning ai driven framework for DDLS Fellows from EMBL`)
- To set the status of the pull request, use the built-in github feature to set the PR as Draft or Ready for review.
- To indicate the type of change (such as bugfix or new feature), use a github pull request label.
- If pr is not ready for review, set it draft. We agreed in the team, that if the PR in the draft state, no one will review it.
- Remember, that you can trigger end2end tests manually
