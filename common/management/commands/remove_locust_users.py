from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from common.management.manage_test_data import TestDataManager

User = get_user_model()


class Command(BaseCommand):
    help = "Deletes users with a specific email identifier"

    def handle(self, *args, **options):
        identifier = "locust_test_user"

        # Find users with the specified email identifier
        users_to_delete = User.objects.filter(email__contains=identifier)

        # Delete all projects first (if any)
        for user in users_to_delete:
            manager = TestDataManager(user_data={"email": user.email})
            manager.delete_all_projects()
            self.stdout.write(self.style.SUCCESS(f'Successfully deleted all projects (if any) for user "{user.email}"'))

        # Delete the users
        user_count = users_to_delete.count()
        users_to_delete.delete()

        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {user_count} users with email containing "{identifier}"')
        )
