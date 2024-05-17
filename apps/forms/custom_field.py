from crispy_forms.layout import Field


class CustomField(Field):
    template = "apps/custom_field.html"

    def __init__(self, *args, **kwargs):
        self.help_message = kwargs.pop("help_message", "")
        super().__init__(*args, **kwargs)

    def render(self, form, context, **kwargs):
        context.update({"help_message": self.help_message})
        return super().render(form, context, **kwargs)
