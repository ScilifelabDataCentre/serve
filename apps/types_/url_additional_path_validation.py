from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator


class UrlAdditionalPathValidation:
    """
    Validating a custom url path addition to the existing URL.
    The validation limits to that additional part only.
    For example, if the original URL is: https://xyz.serve-dev.scilifelab.se,
    and we want to add a path so that it becomes https://xyz.serve-dev.scilifelab.se/new-path,
    then it will only validate 'new-path' part.
    """

    __name = None

    def __init__(self, name: str):
        self.__name = name

    def is_valid(self) -> bool:
        """Determines if the proposed path addition is valid."""
        try:
            self.validate_candidate()
            return True
        except ValidationError:
            return False

    def validate_candidate(self):
        """
        Validates a custom default url path addition.
        The RegexValidator will raise a ValidationError if the input does not match the regular expression.
        It is up to the caller to handle the raised exception if desired.
        """
        error_message = (
            "Your custom default URL is not valid, please correct it. "
            "It must be 1-53 characters long."
            " It can contain only letters, digits, hyphens"
            " ( - ), forward slashes ( / ), and underscores ( _ )."
            " It cannot start or end with a hyphen ( - ) and "
            "cannot start with a forward slash ( / )."
            " It cannot contain consecutive forward slashes ( // )."
        )
        regex_validator = RegexValidator(
            regex=r"^(?!-)(?!/)(?!.*//)[A-Za-z0-9-/_]{1,53}(?<!-)$|^$",
            message=error_message,
        )
        regex_validator(self.__name)
