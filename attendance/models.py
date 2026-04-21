from django.db import models

# Create your models here.
from django.db import models


class Attendance(models.Model):
    student = models.ForeignKey("sds.Student", on_delete=models.CASCADE, related_name="attendances")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=[("Present", "Present"), ("Absent", "Absent")])
    marked_by = models.ForeignKey("sds.TeacherAdmin", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "date")

    def __str__(self):
        return f"{self.student.student_name} - {self.date} - {self.status}"