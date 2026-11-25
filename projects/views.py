import json
from datetime import datetime, timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import staff_required
from tickets.forms import ManualTimeForm, uploaded_files
from tickets.models import TimeEntry
from tickets.services import save_attachments, start_timer, stop_timers

from .forms import MilestoneForm, ProjectForm, TaskCommentForm, TaskForm
from .models import Milestone, Project, Task


@staff_required
def project_list(request):
    projects = Project.objects.select_related("owner").annotate(
        task_total=Count("tasks"),
        task_done=Count("tasks", filter=Q(tasks__status=Task.Status.DONE)),
    )
    return render(request, "projects/list.html", {"projects": projects})


@staff_required
def project_create(request):
    form = ProjectForm(request.POST or None, initial={"owner": request.user})
    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, "Projekt angelegt.")
        return redirect(project)
    return render(request, "projects/form.html", {"form": form, "project": None})


@staff_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Projekt gespeichert.")
        return redirect(project)
    return render(request, "projects/form.html", {"form": form, "project": project})


def _timeline(project, tasks, milestones):
    """Zeitachse: Balken für Aufgaben mit Termin, Markierungen für Meilensteine."""
    bars = []
    for task in tasks:
        if task.due_date is None:
            continue
        start = task.start_date or timezone.localtime(task.created_at).date()
        bars.append({"task": task, "start": min(start, task.due_date), "end": task.due_date})
    marks = [m for m in milestones if m.due_date is not None]
    dates = [b["start"] for b in bars] + [b["end"] for b in bars] + [m.due_date for m in marks]
    if project.start_date:
        dates.append(project.start_date)
    if project.due_date:
        dates.append(project.due_date)
    if not bars and not marks:
        return None

    first, last = min(dates), max(dates)
    span = max((last - first).days, 1)

    def percent(day):
        return round((day - first).days * 100 / span, 1)

    def css(number):
        # Punkt als Dezimalzeichen erzwingen; die deutsche Zahlenformatierung
        # der Vorlagen würde sonst ein Komma in die CSS-Angabe schreiben.
        return f"{number:.1f}"

    today = timezone.localdate()
    for bar in bars:
        left = percent(bar["start"])
        bar["left"] = css(left)
        bar["width"] = css(max(percent(bar["end"]) - left, 1.5))
        bar["late"] = bar["end"] < today and bar["task"].status != Task.Status.DONE
    bars.sort(key=lambda b: (b["start"], b["end"]))
    return {
        "first": first,
        "last": last,
        "bars": bars,
        "marks": [{"milestone": m, "left": css(percent(m.due_date))} for m in marks],
        "today": css(percent(today)) if first <= today <= last else None,
    }


@staff_required
def project_detail(request, pk):
    project = get_object_or_404(Project.objects.select_related("owner"), pk=pk)
    tasks = list(project.tasks.select_related("assignee", "milestone"))
    milestones = list(project.milestones.all())
    for milestone in milestones:
        own = [t for t in tasks if t.milestone_id == milestone.pk]
        milestone.task_total = len(own)
        milestone.task_done = len([t for t in own if t.status == Task.Status.DONE])
        milestone.late = (
            not milestone.done
            and milestone.due_date is not None
            and milestone.due_date < timezone.localdate()
        )
    columns = [
        {
            "key": key,
            "label": label,
            "tasks": [t for t in tasks if t.status == key],
        }
        for key, label in Task.Status.choices
    ]
    return render(
        request,
        "projects/detail.html",
        {
            "project": project,
            "columns": columns,
            "milestones": milestones,
            "milestone_form": MilestoneForm(),
            "timeline": _timeline(project, tasks, milestones),
            "tickets": project.tickets.select_related("assignee")[:50],
        },
    )


@require_POST
@staff_required
def milestone_add(request, pk):
    project = get_object_or_404(Project, pk=pk)
    form = MilestoneForm(request.POST)
    if form.is_valid():
        milestone = form.save(commit=False)
        milestone.project = project
        milestone.save()
    else:
        messages.error(request, "Bitte einen Namen für den Meilenstein angeben.")
    return redirect(project)


@require_POST
@staff_required
def milestone_change(request, pk):
    """Meilenstein als erreicht markieren, wieder öffnen oder löschen."""
    milestone = get_object_or_404(Milestone.objects.select_related("project"), pk=pk)
    project = milestone.project
    if "delete" in request.POST:
        milestone.delete()
    else:
        milestone.done = not milestone.done
        milestone.save()
    return redirect(project)


@staff_required
def task_create(request, pk):
    project = get_object_or_404(Project, pk=pk)
    initial = {"status": request.GET.get("status", Task.Status.TODO)}
    form = TaskForm(request.POST or None, initial=initial, project=project)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.project = project
        task.position = project.tasks.count()
        task.save()
        return redirect(project)
    return render(
        request, "projects/task_form.html", {"form": form, "project": project}
    )


@staff_required
def task_detail(request, pk):
    """Aufgabe ansehen und bearbeiten, mit Kommentaren, Anhängen und Zeiterfassung."""
    task = get_object_or_404(Task.objects.select_related("project", "assignee"), pk=pk)
    project = task.project
    if request.method == "POST" and "delete" in request.POST:
        task.delete()
        messages.info(request, "Aufgabe gelöscht.")
        return redirect(project)
    form = TaskForm(request.POST or None, instance=task, project=project)
    if request.method == "POST" and form.is_valid():
        task = form.save()
        if task.status == Task.Status.DONE:
            stop_timers(task=task)
        messages.success(request, "Aufgabe gespeichert.")
        return redirect(task)

    entries = list(task.time_entries.select_related("user"))
    return render(
        request,
        "projects/task_detail.html",
        {
            "task": task,
            "project": project,
            "form": form,
            "comments": task.comments.select_related("author"),
            "comment_form": TaskCommentForm(),
            "attachments": task.attachments.all(),
            "time_entries": entries,
            "total_seconds": sum(e.seconds for e in entries),
            "timer_running": any(e.running for e in entries),
            "my_timer_running": any(
                e.running and e.user_id == request.user.id for e in entries
            ),
            "manual_time_form": ManualTimeForm(),
        },
    )


@require_POST
@staff_required
def task_time_add(request, pk):
    """Zeit an einer Aufgabe nachtragen."""
    task = get_object_or_404(Task, pk=pk)
    form = ManualTimeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Bitte Datum, Beginn und Dauer angeben.")
        return redirect(task)
    start = timezone.make_aware(
        datetime.combine(form.cleaned_data["date"], form.cleaned_data["start"])
    )
    TimeEntry.objects.create(
        task=task,
        user=request.user,
        started_at=start,
        ended_at=start + timedelta(minutes=form.cleaned_data["minutes"]),
        note=form.cleaned_data["note"] or "nachgetragen",
    )
    return redirect(task)


@require_POST
@staff_required
def task_comment(request, pk):
    task = get_object_or_404(Task, pk=pk)
    form = TaskCommentForm(request.POST, request.FILES)
    files = request.FILES.getlist("files") + request.FILES.getlist("photos")
    if form.is_valid():
        comment = form.save(commit=False)
        comment.task = task
        comment.author = request.user
        comment.save()
        save_attachments(uploaded_files(form.cleaned_data), request.user, task=task)
    elif files and not request.POST.get("body", "").strip():
        # Nur Dateien ohne Text hochladen
        upload_only = TaskCommentForm({"body": "Datei hochgeladen."}, request.FILES)
        if upload_only.is_valid():
            save_attachments(uploaded_files(upload_only.cleaned_data), request.user, task=task)
        else:
            errors = " ".join(e for errs in upload_only.errors.values() for e in errs)
            messages.error(request, errors)
    else:
        errors = " ".join(e for errs in form.errors.values() for e in errs)
        messages.error(request, errors or "Bitte einen Kommentar eingeben.")
    return redirect(task)


@require_POST
@staff_required
def task_timer(request, pk):
    """Uhr für eine Aufgabe starten oder pausieren."""
    task = get_object_or_404(Task, pk=pk)
    if request.POST.get("action") == "pause":
        stop_timers(task=task, user=request.user)
    else:
        if task.status == Task.Status.TODO:
            task.status = Task.Status.DOING
            if task.assignee_id is None:
                task.assignee = request.user
            task.save()
        start_timer(request.user, task=task)
    return redirect(task)


@require_POST
@staff_required
def board_reorder(request, pk):
    """Speichert Spalte und Reihenfolge nach dem Verschieben einer Karte."""
    project = get_object_or_404(Project, pk=pk)
    try:
        data = json.loads(request.body)
        status = data["status"]
        ids = [int(i) for i in data["ids"]]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"ok": False}, status=400)
    if status not in Task.Status.values:
        return JsonResponse({"ok": False}, status=400)

    tasks = {t.pk: t for t in project.tasks.filter(pk__in=ids)}
    for position, task_id in enumerate(ids):
        task = tasks.get(task_id)
        if task is not None:
            task.status = status
            task.position = position
            task.save(update_fields=["status", "position", "updated_at"])
            if status == Task.Status.DONE:
                stop_timers(task=task)
    return JsonResponse({"ok": True})
