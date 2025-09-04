from django.db import models

class UploadedPDF(models.Model):
    pdf_id = models.CharField(max_length=64, unique=True)
    filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(auto_now_add=True)
