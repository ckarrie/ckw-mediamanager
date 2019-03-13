from django import forms
import models


class FileResourceAdminForm(forms.ModelForm):
    class Meta:
        fields = '__all__'
        model = models.FileResource
        widgets = {
            'md_summary': forms.Textarea(attrs={'cols': 30, 'rows': 2})
        }

