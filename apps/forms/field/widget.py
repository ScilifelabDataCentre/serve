from django import forms
from django.template import loader
from django.utils.safestring import mark_safe

from apps.helpers import get_select_options


# Custom Widget that adds boostrap-style input group to the subdomain field
class SubdomainInputGroup(forms.Widget):
    subdomain_template = "apps/partials/subdomain_input_group.html"

    def __init__(self, base_widget, data, *args, **kwargs):
        # Initialise widget and get base instance
        super(SubdomainInputGroup, self).__init__(*args, **kwargs)
        self.base_widget = base_widget(*args, **kwargs)
        self.data = data

    def get_context(self, name, value, attrs=None):
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
