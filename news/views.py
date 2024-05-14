from typing import Any

import markdown
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import NewsObject


def news(request: HttpRequest) -> HttpResponse:
    news_objects = NewsObject.objects.all().order_by("-created_on")
    for news in news_objects:
        news.body_html = markdown.markdown(news.body)
    return render(request, "news/news.html", {"news_objects": news_objects})
