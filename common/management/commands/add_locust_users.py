from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.utils import IntegrityError

User = get_user_model()


class Command(BaseCommand):
    help = "Adds user to database"

    def add_arguments(self, parser):
        parser.add_argument("num_users", type=int)

    def handle(self, *args, **options):
        for i in range(options["num_users"]):
            username = f"locust_test_user_{i}"
            email = f"locust_test_user_{i}@test.uu.net"
            password = "password123"
            try:
                user = User.objects.create_user(username, email, password)
                user.is_active = True
                user.save()
            except IntegrityError:
                self.stdout.write(self.style.WARNING("User with the given username or email already exists."))

        self.stdout.write(self.style.SUCCESS(f"Successfully created {i} users"))
