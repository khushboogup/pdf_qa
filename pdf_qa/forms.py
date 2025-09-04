from django import forms

class PDFUploadForm(forms.Form):
    pdf_file = forms.FileField()
    
class QuestionForm(forms.Form):
    question = forms.CharField(widget=forms.Textarea)
