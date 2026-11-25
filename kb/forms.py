from django import forms

from tickets.forms import MultipleFileField

from .models import Article


class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ["title", "category", "organization", "problem", "solution"]
        widgets = {
            "problem": forms.Textarea(attrs={"rows": 6}),
            "solution": forms.Textarea(attrs={"rows": 12}),
        }


class ArticleFileForm(forms.Form):
    files = MultipleFileField(label="Bilder oder Dateien hochladen")
