from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from apps.models import Subdomain


class SubdomainCandidateName:
    """
    A candidate subdomain name that may or may not be available or allowed.
    """

    __name = None

    def __init__(self, name: str):
        self.__name = name

    def is_available(self) -> bool:
        """Determines if the candidate name is available in Serve."""
        if self.__name == "serve":
            # Reserved words
            return False
        elif Subdomain.objects.filter(subdomain=self.__name).exists():
            return False
        else:
            return True

    def is_valid(self) -> bool:
        """Determines if the candidate name is valid."""
        try:
            self.validate_subdomain()
            return True
        except ValidationError:
            return False

    def validate_subdomain(self):
        """
        Validates a subdomain text.
        The RegexValidator will raise a ValidationError if the input does not match the regular expression.
        It is up to the caller to handle the raised exception if desired.
        """

        # Check if the subdomain adheres to helm rules
        regex_validator = RegexValidator(
            regex=r"^(?!-)[a-z0-9-]{3,53}(?<!-)$",
            message="Subdomain must be 3-53 characters long, contain only lowercase letters, digits, hyphens, "
            "and cannot start or end with a hyphen",
        )

        regex_validator(self.__name)
