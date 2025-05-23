from django.contrib.auth.models import User

from apps.app_registry import APP_REGISTRY
from apps.helpers import create_instance_from_form
from common.models import UserProfile
from projects.models import Environment, Flavor, Project, ProjectTemplate
from projects.tasks import create_resources_from_template


class TestDataManager:
    def __init__(self, user_data=None, project_data=None, app_data=None):
        self.user_data = user_data
        self.project_data = project_data
        self.app_data = app_data

    def create_user(self):
        """Create a regular user with optional profile information."""
        if not all(key in self.user_data for key in ("username", "email", "password")):
            raise ValueError("Missing required user fields")

        user = User.objects.create_user(
            username=self.user_data["username"], email=self.user_data["email"], password=self.user_data["password"]
        )

        # Optional fields
        if all(field in self.user_data for field in ("first_name", "last_name")):
            user.first_name = self.user_data["first_name"]
            user.last_name = self.user_data["last_name"]

        user.is_active = True
        user.save()

        # Profile creation
        if all(field in self.user_data for field in ("department", "affiliation")):
            user_profile = UserProfile.objects.create_user_profile(user)
            user_profile.department = self.user_data["department"]
            user_profile.affiliation = self.user_data["affiliation"]
            user_profile.save()

        return user

    def create_superuser(self):
        """Create a superuser with admin privileges."""
        if not all(key in self.user_data for key in ("username", "email", "password")):
            raise ValueError("Missing required user fields")

        user = User.objects.create_superuser(
            username=self.user_data["username"], email=self.user_data["email"], password=self.user_data["password"]
        )
        user.is_active = True
        user.save()
        return user

    def delete_user(self):
        """Delete user and associated profile. Returns deletion count."""
        if "email" not in self.user_data:
            raise ValueError("Missing email for user deletion")

        user_to_delete = User.objects.filter(email__exact=self.user_data["email"])

        if all(field in self.user_data for field in ("department", "affiliation")):
            UserProfile.objects.filter(user__in=user_to_delete).delete()

        deleted_count, _ = user_to_delete.delete()
        return deleted_count

    def create_project(self):
        """Create a project with associated resources."""
        if not all(key in self.project_data for key in ("project_name", "project_description")):
            raise ValueError("Missing required project fields")
        if "email" not in self.user_data:
            raise ValueError("Missing email for user selection")

        user = User.objects.get(email__exact=self.user_data["email"])
        project_template = ProjectTemplate.objects.get(pk=1)

        project = Project.objects.create_project(
            name=self.project_data["project_name"],
            owner=user,
            description=self.project_data["project_description"],
            project_template=project_template,
            status="created",
        )
        project.save()

        create_resources_from_template(user.username, project.slug, project_template.template)

        return project

    def delete_project(self):
        """Delete specific project. Returns deletion count."""
        if "project_name" not in self.project_data:
            raise ValueError("Missing project name for deletion")
        if "email" not in self.user_data:
            raise ValueError("Missing email for user selection")

        user = User.objects.get(email__exact=self.user_data["email"])
        project_to_delete = Project.objects.filter(owner=user, name=self.project_data["project_name"])
        deleted_count, _ = project_to_delete.delete()
        return deleted_count

    def delete_all_projects(self):
        """Delete all user's projects. Returns deletion count."""
        if "email" not in self.user_data:
            raise ValueError("Missing email for user selection")
        user = User.objects.get(email__exact=self.user_data["email"])
        projects_to_delete = Project.objects.filter(owner=user)
        deleted_count, _ = projects_to_delete.delete()
        return deleted_count

    def create_app(self):
        """Create an application instance with validation."""
        if "project_name" not in self.project_data:
            raise ValueError("Missing project name for deletion")
        if "email" not in self.user_data:
            raise ValueError("Missing email for user selection")
        user = User.objects.get(email__exact=self.user_data["email"])
        project = Project.objects.filter(owner=user, name=self.project_data["project_name"]).first()
        flavor = Flavor.objects.filter(project=project).first()
        environment = Environment.objects.filter(project=project).first()
        app_slug = self.app_data["app_slug"]
        del self.app_data["app_slug"]

        self.app_data["flavor"] = str(flavor.pk)
        self.app_data["environment"] = str(environment.pk)

        # Check if the model form tuple exists
        if app_slug not in APP_REGISTRY:
            raise ValueError(f"Form class not found for app slug {app_slug}")

        form_class = APP_REGISTRY.get_form_class(app_slug)

        # Create form
        form = form_class(self.app_data, project_pk=project.pk)

        if form.is_valid():
            # now create app
            app_id = create_instance_from_form(form, project, app_slug)
        else:
            raise ValueError(f"Form is invalid: {form.errors.as_data()}")

        return app_id
