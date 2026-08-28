from django import forms
from django.template import loader
from django.utils.safestring import mark_safe


# Custom Widget that adds boostrap-style input group to the subdomain field
class SubdomainInputGroup(forms.Widget):
    subdomain_template = "apps/partials/subdomain_input_group.html"

    def __init__(self, base_widget, data, *args, **kwargs):
        # Initialise widget and get base instance
        super().__init__(*args, **kwargs)
        self.base_widget = base_widget(*args, **kwargs)
        self.data = data

    def get_context(self, name, value, attrs=None):
        from apps.helpers import get_select_options

        return {
            "initial_subdomain": value,
            "project_pk": self.data["project_pk"],
            "hidden": self.data["hidden"],
            "subdomain_list": get_select_options(self.data["project_pk"]),
        }

    def render(self, name, value, attrs=None, renderer=None):
        # Render base widget and add bootstrap spans
        context = self.get_context(name, value, attrs)
        template = loader.get_template(self.subdomain_template).render(context)
        return mark_safe(template)


# Select widget for the flavor field that disables flavors when GPU request
# cannot currently be satisfied by the cluster
class FlavorSelect(forms.Select):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Primary keys of flavors that should not be selectable
        self.unavailable_flavors = set()
        # Primary keys of flavors that request a GPU
        self.gpu_flavors = set()

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        # Tag GPU flavors
        option["attrs"]["data-gpu"] = "1" if str(value) in self.gpu_flavors else "0"
        if str(value) in self.unavailable_flavors:
            option["attrs"]["disabled"] = True
            option["label"] = f"{label} (no GPU available at the moment)"
        return option
