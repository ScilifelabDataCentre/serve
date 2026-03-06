from django.contrib.auth.models import User

from apps.app_registry import APP_REGISTRY
from apps.helpers import create_instance_from_form
from common.models import UserProfile
from projects.models import (
    BasicAuth,
    Environment,
    Flavor,
    PersistentVolumeMountPath,
    Project,
    ProjectTemplate,
)
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

        user = self._find_user()
        if user is None:
            user = User.objects.create_user(
                username=self.user_data["username"], email=self.user_data["email"], password=self.user_data["password"]
            )
        else:
            user.set_password(self.user_data["password"])
            user.email = self.user_data["email"]

        # Optional fields
        if all(field in self.user_data for field in ("first_name", "last_name")):
            user.first_name = self.user_data["first_name"]
            user.last_name = self.user_data["last_name"]

        user.is_active = True
        user.save()

        # Always ensure a UserProfile exists (defensive against post_save signals)
        user_profile, _ = UserProfile.objects.get_or_create(user=user)

        # Set affiliations if provided
        if "affiliations" in self.user_data:
            user_profile.affiliations = self.user_data["affiliations"]
            user_profile.save()

        return user

    def create_superuser(self):
        """Create a superuser with admin privileges."""
        if not all(key in self.user_data for key in ("username", "email", "password")):
            raise ValueError("Missing required user fields")

        user = self._find_user()
        if user is None:
            user = User.objects.create_superuser(
                username=self.user_data["username"], email=self.user_data["email"], password=self.user_data["password"]
            )
        else:
            user.set_password(self.user_data["password"])
            user.email = self.user_data["email"]
            user.is_staff = True
            user.is_superuser = True
        user.is_active = True
        user.save()
        return user

    def delete_user(self):
        """Delete user and associated profile. Returns deletion count."""
        if not any(key in self.user_data for key in ("email", "username")):
            raise ValueError("Missing username/email for user deletion")

        user_to_delete = User.objects.none()
        if "username" in self.user_data and self.user_data["username"]:
            user_to_delete = user_to_delete | User.objects.filter(username__exact=self.user_data["username"])
        if "email" in self.user_data and self.user_data["email"]:
            user_to_delete = user_to_delete | User.objects.filter(email__exact=self.user_data["email"])
        user_to_delete = user_to_delete.distinct()

        if not user_to_delete.exists():
            return 0

        Project.objects.filter(owner__in=user_to_delete).delete()
        BasicAuth.objects.filter(owner__in=user_to_delete).delete()
        UserProfile.objects.filter(user__in=user_to_delete).delete()

        deleted_count, _ = user_to_delete.delete()
        return deleted_count

    def create_project(self):
        """Create a project with associated resources."""
        if not all(key in self.project_data for key in ("project_name", "project_description")):
            raise ValueError("Missing required project fields")
        user = self._find_user()
        if user is None:
            raise ValueError("User not found for provided username/email")

        existing_project = Project.objects.filter(owner=user, name=self.project_data["project_name"]).first()
        if existing_project:
            if existing_project.description != self.project_data["project_description"]:
                existing_project.description = self.project_data["project_description"]
                existing_project.save(update_fields=["description"])
            return existing_project

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
        user = self._find_user()
        if user is None:
            raise ValueError("User not found for provided username/email")
        project_to_delete = Project.objects.filter(owner=user, name=self.project_data["project_name"])
        deleted_count, _ = project_to_delete.delete()
        return deleted_count

    def delete_all_projects(self):
        """Delete all user's projects. Returns deletion count."""
        user = self._find_user()
        if user is None:
            raise ValueError("User not found for provided username/email")
        projects_to_delete = Project.objects.filter(owner=user)
        deleted_count, _ = projects_to_delete.delete()
        return deleted_count

    def create_app(self):
        """Create an application instance with validation."""
        if "project_name" not in self.project_data:
            raise ValueError("Missing project name for deletion")
        user = self._find_user()
        if user is None:
            raise ValueError("User not found for provided username/email")
        project = Project.objects.filter(owner=user, name=self.project_data["project_name"]).first()
        if project is None:
            raise ValueError(f"Project '{self.project_data['project_name']}' not found for user '{user.username}'")

        app_slug = self.app_data["app_slug"]
        if app_slug not in APP_REGISTRY:
            raise ValueError(f"Form class not found for app slug {app_slug}")

        orm_model = APP_REGISTRY.get_orm_model(app_slug)
        existing_app = orm_model.objects.filter(
            owner=user,
            project=project,
            name=self.app_data.get("name"),
            deleted_on__isnull=True,
        ).first()
        if existing_app:
            return existing_app.id

        flavor = Flavor.objects.filter(project=project).first()
        environment = Environment.objects.filter(project=project).first()

        del self.app_data["app_slug"]

        self.app_data["flavor"] = str(flavor.pk)
        self.app_data["environment"] = str(environment.pk)

        # Handle mount_path: if not specified or set to "default", use the default mount path for the project
        if "mount_path" not in self.app_data or self.app_data.get("mount_path") == "default":
            default_mount_path = PersistentVolumeMountPath.objects.filter(
                volume__project=project, is_default=True
            ).first()
            if default_mount_path:
                self.app_data["mount_path"] = str(default_mount_path.pk)
            # If no default mount path exists, leave it unset (None/no storage)

        # Check if the model form tuple exists
        form_class = APP_REGISTRY.get_form_class(app_slug)

        # Create form
        form = form_class(self.app_data, project_pk=project.pk)

        if form.is_valid():
            # now create app
            app_id = create_instance_from_form(form, project, app_slug)
        else:
            raise ValueError(f"Form is invalid: {form.errors.as_data()}")

        return app_id

    def _find_user(self):
        if not self.user_data:
            return None

        username = self.user_data.get("username")
        email = self.user_data.get("email")

        if username:
            user = User.objects.filter(username__exact=username).first()
            if user:
                return user

        if email:
            user = User.objects.filter(email__exact=email).first()
            if user:
                return user

        return None
