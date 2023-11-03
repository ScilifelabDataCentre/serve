
from django.shortcuts import render
from .models import NewsObject

def news(request):
    news_objects = NewsObject.objects.all()
    return render(request, 'portal/news.html', locals())
