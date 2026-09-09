from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("apps", "0044_alter_baseappinstance_latest_user_action"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customappinstance",
            name="access",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("project", "Project"),
                    ("private", "Private"),
                    ("public", "Public"),
                    ("link", "Link"),
                ],
                default="draft",
                help_text="The chosen Permission level determines who can access the application.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="dashinstance",
            name="access",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("project", "Project"),
                    ("private", "Private"),
                    ("public", "Public"),
                    ("link", "Link"),
                ],
                default="draft",
                help_text="The chosen Permission level determines who can access the application.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="gradioinstance",
            name="access",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("project", "Project"),
                    ("private", "Private"),
                    ("public", "Public"),
                    ("link", "Link"),
                ],
                default="draft",
                help_text="The chosen Permission level determines who can access the application.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="shinyinstance",
            name="access",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("project", "Project"),
                    ("private", "Private"),
                    ("public", "Public"),
                    ("link", "Link"),
                ],
                default="draft",
                help_text="The chosen Permission level determines who can access the application.",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="streamlitinstance",
            name="access",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("project", "Project"),
                    ("private", "Private"),
                    ("public", "Public"),
                    ("link", "Link"),
                ],
                default="draft",
                help_text="The chosen Permission level determines who can access the application.",
                max_length=20,
            ),
        ),
    ]
