# Chart

## Description

Describe your changes. 

If the pull request contains a new chart, you should describe the service it provides, the origin of its image, and any other things that may be relevant.

## Types of changes

What types of changes does your code introduce to STACKn?

- [ ] Hotfix (fixing a critical bug in production)
- [ ] Bugfix
- [ ] New chart
- [ ] Documentation update

## Checklist

### Chart

- [ ] The image is not running as root
- [ ] The file system is read-only
- [ ] The service account token is not mounted (not applicable if the token is required for the funtion of the pod)
- [ ] A `readinessProbe` is included
- [ ] NetworkPolicies are included to keep the network access to a minimum
- [ ] Resource limits have been set (CPU, memory, and ephemeral storage), both a good estimate of the requested resources, and the maximum resources the pods may use 
- [ ] A unique service account is created
- [ ] Any sensitive data is stored in a `Secret`

### General

- [ ] I have included a link to the issue on GitHub or JIRA (if any)
- [ ] I have included migration files (if there are changes to the model classes)
- [ ] I have read the [CONTRIBUTING](https://github.com/scaleoutsystems/stackn/blob/master/CONTRIBUTING.md) doc
- [ ] I have included tests to complement my changes
- [ ] I have updated the related documentation (if necessary) 
- [ ] I have updated the release notes (docs/releasenotes.md)
- [ ] I have added a reviewer for this pull request
- [ ] I have added myself as an author for this pull request

## Further comments

Anything else you think we should know before merging your code!
