from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0043_customappinstance_subjects_keywords_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="baseappinstance",
            name="latest_user_action",
            field=models.CharField(
                choices=[
                    ("Creating", "Creating"),
                    ("Changing", "Changing"),
                    ("Deleting", "Deleting"),
                    ("SystemDeleting", "SystemDeleting"),
                    ("Redeploying", "Redeploying"),
                    ("Draft", "Draft"),
                ],
                default="Creating",
                max_length=15,
            ),
        ),
    ]
