from itertools import zip_longest

from django import forms
from django.core.exceptions import ValidationError

from apps.environment_variables import (
    validate_environment_configuration,
    validate_environment_name_collisions,
    validate_environment_overrides,
    validate_project_secret_imports,
)
from apps.forms.field.common import SRVCommonDivField
from apps.models import AppEnvironmentSecret
from common.privileges import has_privileged_access


class EnvironmentVariablesWidget(forms.Widget):
    template_name = "apps/widgets/environment_variables.html"

    class Media:
        js = ("js/environment_variables.js",)

    def value_omitted_from_data(self, data, files, name):
        return False

    def value_from_datadict(self, data, files, name):
        if name in data:
            return data.get(name)

        def get_values(field_name):
            if hasattr(data, "getlist"):
                return data.getlist(field_name)
            value = data.get(field_name, [])
            return value if isinstance(value, list) else [value]

        names = get_values(f"{name}_config_name")
        values = get_values(f"{name}_config_value")
        return list(zip_longest(names, values, fillvalue=""))

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        if isinstance(value, list):
            rows = value
        elif isinstance(value, dict):
            rows = [
                (key, source["value"])
                for key, source in value.items()
                if isinstance(source, dict) and isinstance(source.get("value"), str)
            ]
        else:
            rows = []
        context["widget"]["config_rows"] = rows
        return context


class EnvironmentVariablesField(forms.Field):
    def to_python(self, value):
        if not isinstance(value, list):
            raise ValidationError("Enter environment variables using the name and value inputs.")
        config = {}
        for name, ordinary_value in value:
            if not name and not ordinary_value:
                continue
            if name in config:
                raise ValidationError(f"Duplicate environment variable: {name}")
            config[name] = {"value": ordinary_value}
        return config


class EnvironmentSecretSelectionsField(forms.MultipleChoiceField):
    def prepare_value(self, value):
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return [
                f'{item["name"]}:{key}'
                for item in value
                for key in (["*"] if item.get("all") is True else item.get("keys", []))
            ]
        return value

    def clean(self, value):
        selected = super().clean(value)
        grouped = {}
        for token in selected:
            name, key = token.split(":", 1)
            grouped.setdefault(name, set()).add(key)
        return [
            {"name": name, "all": True} if "*" in keys else {"name": name, "keys": sorted(keys)}
            for name, keys in sorted(grouped.items())
        ]

    def has_changed(self, initial, data):
        try:
            return self.clean(self.prepare_value(initial) or []) != self.clean(data or [])
        except ValidationError:
            return True


class EnvironmentVariablesMixin:
    """Expose private environment settings only to project-authorized privileged app editors."""

    def _setup_form_fields(self):
        super()._setup_form_fields()
        self.can_edit_environment = has_privileged_access(getattr(self.request, "user", None), self.project)
        if not self.can_edit_environment:
            self.fields.pop("environment_variables", None)
            self.fields.pop("environment_secret_imports", None)
            return
        field = EnvironmentVariablesField(
            required=False,
            widget=EnvironmentVariablesWidget,
            label="Environment variables",
        )
        self.fields["environment_variables"] = field
        approvals = list(AppEnvironmentSecret.objects.filter(project=self.project).values("name", "keys"))
        groups = {approval["name"]: set(approval["keys"]) for approval in approvals}
        for selection in self.instance.environment_secret_imports:
            if isinstance(selection, dict) and isinstance(selection.get("name"), str):
                groups.setdefault(selection["name"], set()).update(selection.get("keys", []))
        choices = [
            (f"{name}:{key}", f"{name} / {key}") for name, keys in groups.items() for key in ["*", *sorted(keys)]
        ]
        self.fields["environment_secret_imports"] = EnvironmentSecretSelectionsField(
            choices=choices,
            required=False,
        )
        self.fields["environment_secret_imports"].secret_groups = [
            {
                "name": name,
                "all_token": f"{name}:*",
                "keys": [{"name": key, "token": f"{name}:{key}"} for key in sorted(keys)],
            }
            for name, keys in sorted(groups.items())
        ]
        if self.is_bound:
            if hasattr(self.data, "getlist"):
                selected_tokens = self.data.getlist("environment_secret_imports")
            else:
                selected_tokens = self.data.get("environment_secret_imports", [])
                selected_tokens = selected_tokens if isinstance(selected_tokens, list) else [selected_tokens]
        else:
            selected_tokens = (
                self.fields["environment_secret_imports"].prepare_value(self.instance.environment_secret_imports) or []
            )
        selected_by_name = {}
        for token in selected_tokens:
            if isinstance(token, str) and ":" in token:
                name, key = token.split(":", 1)
                selected_by_name.setdefault(name, set()).add(key)
        secret_rows = []
        for name, keys in sorted(selected_by_name.items()):
            if name not in groups:
                continue
            if "*" in keys:
                value_label = "All keys"
                display_label = "All keys"
            else:
                display_label = ", ".join(sorted(keys))
                value_label = f"{len(keys)} {'key' if len(keys) == 1 else 'keys'} selected"
            secret_rows.append({"name": name, "value_label": value_label, "display_label": display_label})
        self.fields["environment_secret_imports"].secret_rows = secret_rows
        self.fields["environment_secret_imports"].blank_row = {"name": ""}

    def get_environment_variables_layout(self):
        if "environment_variables" not in self.fields:
            return []
        return [
            SRVCommonDivField(
                "environment_variables",
                template="apps/environment_variables_field.html",
            ),
            SRVCommonDivField(
                "environment_secret_imports",
                tooltip=False,
                template="apps/environment_secret_imports_field.html",
            ),
        ]

    def clean(self):
        cleaned_data = super().clean()
        if not self.can_edit_environment and any(
            name in self.data
            for name in (
                "environment_variables",
                "environment_variables_config_name",
                "environment_variables_config_value",
                "environment_secret_imports",
            )
        ):
            raise forms.ValidationError(
                "Only privileged users with access to this project and administrators can edit environment variables."
            )
        if self.can_edit_environment and all(
            name in cleaned_data for name in ("environment_variables", "environment_secret_imports")
        ):
            try:
                validate_environment_name_collisions(
                    cleaned_data["environment_variables"], self._environment_secret_names
                )
            except ValidationError as exc:
                self.add_error("environment_secret_imports", exc)
        return cleaned_data

    def clean_environment_variables(self):
        value = self.cleaned_data["environment_variables"]
        validate_environment_configuration(value, is_shiny=self._meta.model._meta.model_name == "shinyinstance")
        validate_environment_overrides(value, self.instance.k8s_values_override)
        return value

    def clean_environment_secret_imports(self):
        imports = self.cleaned_data["environment_secret_imports"]
        self._environment_secret_names = validate_project_secret_imports(
            imports, self.project_pk, is_shiny=self._meta.model._meta.model_name == "shinyinstance"
        )
        validate_environment_overrides({}, self.instance.k8s_values_override, secret_imports=imports)
        return imports
