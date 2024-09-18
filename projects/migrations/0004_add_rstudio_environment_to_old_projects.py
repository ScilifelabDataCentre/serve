# Written manually by Nikita Churikov on 2024-09-18

from django.db import migrations


# create a new "Default Rstudio" environment in every project that does not have it
def create_default_rstudio_environments(apps, schema_editor):
    Project = apps.get_model("projects", "Project")
    Environment = apps.get_model("projects", "Environment")
    AppsTemplate = apps.get_model("apps", "Apps")
    # check if RStudio app template exists. It doesn't exist on the first migration
    if not AppsTemplate.objects.filter(name="RStudio").exists():
        RStudioTemplate = AppsTemplate.objects.get(name="RStudio")
        RStudioInstance = apps.get_model("apps", "RStudioInstance")
        for project in Project.objects.all():
            env = Environment.objects.create(
                app=RStudioTemplate,
                project=project,
                name="Default RStudio",
                image="serve-rstudio:231030-1146",
                repository="ghcr.io/scilifelabdatacentre",
            )
            env.save()
            for rstudio_instance in RStudioInstance.objects.filter(project=project):
                rstudio_instance.environment = env
                rstudio_instance.save()


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0003_alter_environment_rename_jupyter_lab_to_default_jupyter"),
        ("apps", "0012_rstudioinstance_environment"),
    ]

    operations = [
        migrations.RunPython(create_default_rstudio_environments),
    ]
