class ProjectCreationException(Exception):
    pass


class ProjectLimitReachedException(ProjectCreationException):
    pass


class ModelDeploymentCreationException(Exception):
    pass
