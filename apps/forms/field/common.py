from crispy_forms.layout import Div

from apps.constants import HELP_MESSAGE_MAP
from apps.forms.field.custom import CustomField


class SRVCommonDivField(Div):
    """
    This class is the most common field used in the apps creation forms.
    Resulting field has a question_mark with tooltip next to the label. So "Name (?)" will have a tooltip.
    The text in the tooltip is defined in apps.constants.HELP_MESSAGE_MAP.
    The CustomField class just inherits the crispy_forms.layout.Field class and adds the
    help_message attribute to it. The template then uses it to render the tooltip for all fields
    using this class.
    """

    def __init__(self, field_name: str, spinner=False, css_class=None, template="apps/custom_field.html", **kwargs):
        if css_class is None and spinner:
            css_class = "form-input-with-spinner"
        base_args = dict(
            css_class="form-control form-control-with-spinner" if spinner else "form-control",
            wrapper_class="mb-3",
            rows=3,
            help_message=HELP_MESSAGE_MAP.get(field_name, ""),
            spinner=spinner,
        )
        base_args.update(kwargs)
        field_ = CustomField(field_name, **base_args)
        field_.set_template(template)
        super().__init__(field_, css_class=css_class)
