from crispy_forms.layout import Field


class CustomField(Field):
    template = "apps/custom_field.html"

    def __init__(self, *args, **kwargs):
        self.help_message = kwargs.pop("help_message", "")
        self.spinner = kwargs.pop("spinner", False)
        self.tooltip = kwargs.pop("tooltip", True)
        self.context = kwargs
        super().__init__(*args, **kwargs)

    def render(self, form, context, **kwargs):
        context.update({"help_message": self.help_message, "spinner": self.spinner, "tooltip": self.tooltip})
        context.update(self.context)
        return super().render(form, context, **kwargs)

    def set_template(self, name: str):
        self.template = name
