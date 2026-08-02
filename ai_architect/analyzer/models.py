from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class UserProfile(models.Model):
    """Extended user profile information"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.URLField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s profile"


class Project(models.Model):
    """Represents a GitHub repository to be analyzed"""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    github_url = models.URLField(unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    is_private = models.BooleanField(default=False)
    # For tracking analysis status
    last_analyzed = models.DateTimeField(null=True, blank=True)
    analysis_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('cloning', 'Cloning'),
            ('processing', 'Processing'),
            ('analyzing', 'Analyzing'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ],
        default='pending'
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.github_url})"

    class Meta:
        ordering = ['-created_at']


class AnalysisJob(models.Model):
    """Tracks individual analysis runs"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='analysis_jobs')
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('running', 'Running'),
            ('cloning', 'Cloning'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed')
        ],
        default='pending'
    )
    # Store the commit hash or version analyzed
    commit_hash = models.CharField(max_length=100, blank=True)
    # Results summary
    files_analyzed = models.IntegerField(default=0)
    functions_found = models.IntegerField(default=0)
    classes_found = models.IntegerField(default=0)
    methods_found = models.IntegerField(default=0)
    relationships_found = models.IntegerField(default=0)
    # Progress tracking (0-100)
    progress = models.IntegerField(default=0)
    # Logs
    logs = models.TextField(blank=True, null=True)
    # Timing
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analysis of {self.project.name} - {self.status}"

    class Meta:
        ordering = ['-created_at']


# Optional: Models that map to existing analysis tables
# These would allow Django ORM access to the analysis results
class File(models.Model):
    """Maps to the 'files' table from the analysis"""
    path = models.CharField(max_length=500, unique=True)
    content_hash = models.CharField(max_length=64)  # SHA-256 hash
    # We won't use the id field from the original table as FK,
    # instead we'll use this as our primary key and link via the path
    # Or we could keep the id and manage it carefully

    class Meta:
        db_table = 'files'
        # Don't let Django manage this table since it's created by the Python script
        managed = False

    def __str__(self):
        return self.path


class CodeEntity(models.Model):
    """Maps to the 'code_entities' table from the analysis"""
    TYPE_CHOICES = [
        ('function', 'Function'),
        ('class', 'Class'),
        ('method', 'Method'),
    ]

    # We'll link to File via path or foreign key if we manage the relationship
    file_path = models.CharField(max_length=500)  # Could be FK to File if we managed it
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    start_line = models.IntegerField()
    end_line = models.IntegerField()
    signature = models.TextField(blank=True)

    class Meta:
        db_table = 'code_entities'
        managed = False

    def __str__(self):
        return f"{self.name} ({self.type})"


class Relationship(models.Model):
    """Maps to the 'relationships' table from the analysis"""
    caller = models.ForeignKey(CodeEntity, on_delete=models.CASCADE, related_name='calls_made')
    callee = models.ForeignKey(CodeEntity, on_delete=models.CASCADE, related_name='calls_received')
    file_path = models.CharField(max_length=500)  # Could be FK to File
    line_number = models.IntegerField()

    class Meta:
        db_table = 'relationships'
        managed = False

    def __str__(self):
        return f"{self.caller} -> {self.callee}"