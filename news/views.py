
from django.shortcuts import render
from .models import NewsObject

def news(request):
    news_objects = NewsObject.objects.all().order_by('-created_on')
    return render(request, 'portal/news.html', locals())
