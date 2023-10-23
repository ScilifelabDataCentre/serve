from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from ..models import ProjectTemplate

User = get_user_model()

test_user = {
    "username": "foo1",
    "email": "foo@test.com",
    "password": "bar"
}

class ProjectCreateViewTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(test_user["username"], test_user["email"], test_user["password"])
        self.client.login(username=test_user["email"], password=test_user["password"])

        project_template = ProjectTemplate(name="Template")
        project_template.save()

        print("project_template.pk")
        print(project_template.pk)
        self.template_id = project_template.pk

    def test_project_create_get(self):
        response = self.client.get(
            "/projects/create?template=Template",
        )

        response.status_code

        self.assertEqual(response.status_code, 200)

        self.assertIsNotNone(response.context["template"])
        self.assertTrue(response.context["template"].id > 0)

    def test_project_create_post(self):
        with patch("projects.tasks.create_resources_from_template.delay") as mock_task:
            response = self.client.post(
                "/projects/create?template=Template",
                {
                    "name": "My Project",
                    "desciption": "My description",
                    "template_id": self.template_id,
                },
            )

            response.status_code

            self.assertEqual(response.status_code, 302)

            mock_task.assert_called_once()
