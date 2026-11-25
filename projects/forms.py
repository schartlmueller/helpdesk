from django import forms
from django.contrib.auth import get_user_model

from tickets.forms import CameraField, MultipleFileField, user_label

from .models import Milestone, Project, Task, TaskComment


def _date_input():
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def _staff_users():
    return get_user_model().objects.filter(is_staff=True, is_active=True)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description", "status", "owner", "organization", "start_date", "due_date"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "start_date": _date_input(),
            "due_date": _date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["owner"].queryset = _staff_users()
        self.fields["owner"].label_from_instance = user_label


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "description",
            "status",
            "priority",
            "assignee",
            "milestone",
            "start_date",
            "due_date",
            "planned_for",
            "estimated_minutes",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "start_date": _date_input(),
            "due_date": _date_input(),
            "planned_for": _date_input(),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = _staff_users()
        self.fields["assignee"].label_from_instance = user_label
        self.fields["milestone"].queryset = project.milestones.all()


class MilestoneForm(forms.ModelForm):
    class Meta:
        model = Milestone
        fields = ["name", "due_date"]
        widgets = {"due_date": _date_input()}


class TaskCommentForm(forms.ModelForm):
    photos = CameraField()
    files = MultipleFileField()

    class Meta:
        model = TaskComment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}
