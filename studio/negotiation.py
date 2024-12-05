from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.parsers import BaseParser
from rest_framework.renderers import BaseRenderer
from rest_framework.request import Request


class IgnoreClientContentNegotiation(BaseContentNegotiation):
    """
    This content negotiation class always selects the first parser or renderer

    See https://www.django-rest-framework.org/api-guide/content-negotiation/#custom-content-negotiation
    """

    def select_parser(self, request: Request, parsers: list[BaseParser]) -> BaseParser:
        """
        Select the first parser in the `.parser_classes` list.
        """
        return parsers[0]

    def select_renderer(
            self, request: Request, renderers: list[BaseRenderer], format_suffix: str | None
    ) -> tuple[BaseRenderer, str]:
        """
        Select the first renderer in the `.renderer_classes` list.
        """
        return (renderers[0], renderers[0].media_type)
