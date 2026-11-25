from django.contrib import admin

from .models import Article, ArticleFile


class ArticleFileInline(admin.TabularInline):
    model = ArticleFile
    extra = 0


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "category", "views", "updated_at"]
    list_filter = ["status", "category"]
    search_fields = ["title", "problem", "solution"]
    raw_id_fields = ["source_ticket"]
    inlines = [ArticleFileInline]
