from django.db import models

class CurriculumPassage(models.Model):
    chapter = models.CharField(max_length=100) # e.g. "Chapter 5: C Programming"
    topic = models.CharField(max_length=100)   # e.g. "Loops & Iteration"
    language = models.CharField(max_length=5, default='bn')
    content = models.TextField()
    source_ref = models.CharField(max_length=100) # e.g. "NCTB Board Book Page 142"
    chroma_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.chapter} - {self.topic} ({self.source_ref})"
