from django.shortcuts import render

# Create your views here.
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import datetime, timedelta
import json
import csv
import os
import re

import pandas as pd
from pypdf import PdfReader

from sds.models import TeacherAdmin, Subject
from .models import SubjectSchedule, ScheduleEntry, UploadedSchedule


def serialize_schedule_entry(entry):
    """Convert a schedule entry into JSON-safe data for templates and APIs."""
    return {
        'id': entry.id,
        'date': entry.date.strftime('%Y-%m-%d'),
        'date_display': entry.date.strftime('%d-%m-%Y'),
        'subject': entry.subject.subject,
        'topic': entry.topic,
        'chapter': entry.chapter,
        'notes': entry.notes,
        'teacher': entry.teacher.name if entry.teacher else '-',
        'teacher_id': entry.teacher_id,
        'duration': entry.duration,
        'duration_display': entry.get_duration_display(),
        'lecture_number': entry.lecture_number,
        'is_completed': entry.is_completed,
    }


def serialize_schedule_entries(entries):
    """Serialize schedule entries for JSON output."""
    return [serialize_schedule_entry(entry) for entry in entries]


def serialize_uploaded_file(uploaded_file):
    """Convert an uploaded schedule file into JSON-safe data."""
    return {
        'id': uploaded_file.id,
        'file_name': uploaded_file.file_name,
        'file_type': uploaded_file.get_file_type_display(),
        'file_url': uploaded_file.file.url if uploaded_file.file else '',
        'grade': uploaded_file.grade,
        'board': uploaded_file.board,
        'batch': uploaded_file.batch,
        'uploaded_by': uploaded_file.uploaded_by.get_full_name() or uploaded_file.uploaded_by.username,
        'uploaded_at': uploaded_file.uploaded_at.strftime('%Y-%m-%d %H:%M:%S'),
        'uploaded_at_display': uploaded_file.uploaded_at.strftime('%d-%m-%Y %I:%M %p'),
    }


def serialize_uploaded_files(uploaded_files):
    """Serialize uploaded schedule files for JSON output."""
    return [serialize_uploaded_file(uploaded_file) for uploaded_file in uploaded_files]


def normalize_text(value):
    """Normalize extracted text for display."""
    if value is None:
        return ""

    cleaned = str(value).replace("\u2013", "-").replace("\u2014", "-").replace("\xa0", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def excel_cell_to_string(value):
    """Format Excel cell values for JSON output."""
    if pd.isna(value):
        return ""
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%d-%m-%Y")
        except Exception:
            pass
    return normalize_text(value)


def read_pdf_lines(file_path):
    """Extract non-empty lines from a PDF file."""
    reader = PdfReader(file_path)
    lines = []

    for page in reader.pages:
        text = page.extract_text() or ""
        for raw_line in text.splitlines():
            cleaned = normalize_text(raw_line)
            if cleaned:
                lines.append(cleaned)

    return lines


def chunk_lines(lines, chunk_size=25):
    """Split raw text into smaller blocks for display."""
    return [" ".join(lines[index:index + chunk_size]) for index in range(0, len(lines), chunk_size)]


def parse_chapter_line(line):
    """Parse chapter summary lines from lecture-plan PDFs."""
    parts = [normalize_text(part) for part in line.split("|") if normalize_text(part)]
    return {
        "title": parts[0] if parts else line,
        "schedule": " | ".join(parts[1:]) if len(parts) > 1 else "",
    }


def parse_lecture_block(block_lines):
    """Convert one lecture block into structured lecture data."""
    if not block_lines:
        return None

    cleaned_lines = [normalize_text(line) for line in block_lines if normalize_text(line)]
    if not cleaned_lines:
        return None

    combined = normalize_text(" ".join(cleaned_lines))
    lecture_match = re.match(r"^L(?P<number>\d+)\s+(?P<body>.+)$", combined, re.IGNORECASE)
    if not lecture_match:
        return None

    lecture_number = lecture_match.group("number")
    body = lecture_match.group("body")

    dpp_match = re.search(r"\bDPP\s+(?P<dpp>\d+)\s+(?P<duration>\d+\s*min)\b", body, re.IGNORECASE)
    dpp = dpp_match.group("dpp") if dpp_match else ""
    duration = dpp_match.group("duration") if dpp_match else ""
    description = re.sub(r"\bDPP\s+\d+\s+\d+\s*min\b", "", body, flags=re.IGNORECASE).strip()

    first_line = re.sub(r"^L\d+\s+", "", cleaned_lines[0], flags=re.IGNORECASE).strip()
    if len(cleaned_lines) > 1 and ";" not in first_line:
        title_lines = [first_line]
        for extra_line in cleaned_lines[1:]:
            if ";" in extra_line or "DPP" in extra_line.upper() or len(extra_line.split()) > 8:
                break
            title_lines.append(extra_line)
        title = normalize_text(" ".join(title_lines))
    else:
        title = normalize_text(first_line.split(";", 1)[0])

    return {
        "lecture_no": lecture_number,
        "title": title or description[:80],
        "details": normalize_text(description),
        "dpp": dpp,
        "duration": duration,
    }


def parse_lecture_plan_pdf(lines):
    """Parse lecture-by-lecture PDFs like the Chemistry sample."""
    chapters = []
    lectures = []
    current_block = []

    for line in lines:
        if re.match(r"^Chapter\s+\d+:", line, re.IGNORECASE):
            chapters.append(parse_chapter_line(line))
            continue

        if line.startswith("L#") or line.startswith("CHEMISTRY TEACHING PLAN") or line.startswith("THE RANKERS ACADEMY"):
            continue

        if re.match(r"^L\d+\b", line, re.IGNORECASE):
            lecture = parse_lecture_block(current_block)
            if lecture:
                lectures.append(lecture)
            current_block = [line]
            continue

        if current_block:
            current_block.append(line)

    lecture = parse_lecture_block(current_block)
    if lecture:
        lectures.append(lecture)

    return {
        "parse_type": "lecture_plan",
        "summary": f"{len(lectures)} lectures parsed",
        "chapters": chapters,
        "lectures": lectures,
        "phases": [],
        "sheets": [],
        "text_blocks": [],
    }


def parse_phase_plan_pdf(lines):
    """Parse phase-wise academic planner PDFs like the JEE planner sample."""
    phases = []
    current_phase = None
    ignored_prefixes = (
        "HOLIDAYS:",
        "FACULTY TEACHING PLAN",
        "THE RANKERS ACADEMY",
        "DPP POLICY:",
        "Physics (",
    )

    for line in lines:
        if line.startswith(ignored_prefixes):
            continue

        if re.match(r"^Phase\s+\d+", line, re.IGNORECASE):
            if current_phase:
                phases.append(current_phase)
            current_phase = {
                "phase": line,
                "overview": "",
                "items": [],
                "milestones": [],
            }
            continue

        if not current_phase:
            continue

        if not current_phase["overview"]:
            current_phase["overview"] = line
            continue

        if re.search(r"\bUT\s*\d+\b|Grand Test|Final mock|Last class|DUSSEHRA|DIWALI|SUMMER HOLIDAY|REVISION PLAN", line, re.IGNORECASE):
            current_phase["milestones"].append(line)
        else:
            current_phase["items"].append(line)

    if current_phase:
        phases.append(current_phase)

    return {
        "parse_type": "phase_plan",
        "summary": f"{len(phases)} phases parsed",
        "chapters": [],
        "lectures": [],
        "phases": phases,
        "sheets": [],
        "text_blocks": [],
    }


def parse_excel_schedule(file_path):
    """Parse Excel files into sheet/row data."""
    workbook = pd.ExcelFile(file_path)
    sheets = []

    for sheet_name in workbook.sheet_names:
        dataframe = workbook.parse(sheet_name).fillna("")
        if dataframe.empty and len(dataframe.columns) == 0:
            continue

        columns = [excel_cell_to_string(column) for column in dataframe.columns.tolist()]
        rows = []

        for _, row in dataframe.iterrows():
            values = [excel_cell_to_string(value) for value in row.tolist()]
            if any(value for value in values):
                rows.append(values)

        sheets.append({
            "name": sheet_name,
            "columns": columns,
            "rows": rows,
        })

    return {
        "parse_type": "spreadsheet",
        "summary": f"{len(sheets)} sheet(s) parsed",
        "chapters": [],
        "lectures": [],
        "phases": [],
        "sheets": sheets,
        "text_blocks": [],
    }


def parse_pdf_schedule(file_path):
    """Parse known PDF schedule layouts into structured content."""
    lines = read_pdf_lines(file_path)

    if any(re.match(r"^L\d+\b", line, re.IGNORECASE) for line in lines):
        return parse_lecture_plan_pdf(lines)

    if any(re.match(r"^Phase\s+\d+", line, re.IGNORECASE) for line in lines):
        return parse_phase_plan_pdf(lines)

    return {
        "parse_type": "raw_text",
        "summary": f"{len(lines)} lines extracted",
        "chapters": [],
        "lectures": [],
        "phases": [],
        "sheets": [],
        "text_blocks": chunk_lines(lines[:150]),
    }


def parse_uploaded_schedule(uploaded_schedule):
    """Build display-ready parsed content for an uploaded schedule."""
    serialized = serialize_uploaded_file(uploaded_schedule)

    try:
        if uploaded_schedule.file_type == "PDF":
            parsed_data = parse_pdf_schedule(uploaded_schedule.file.path)
        else:
            parsed_data = parse_excel_schedule(uploaded_schedule.file.path)
    except Exception as exc:
        parsed_data = {
            "parse_type": "raw_text",
            "summary": "File imported, but automatic parsing could not complete.",
            "chapters": [],
            "lectures": [],
            "phases": [],
            "sheets": [],
            "text_blocks": [normalize_text(exc)],
        }

    return {
        **serialized,
        **parsed_data,
    }


def get_teacher_admin(user):
    """Get TeacherAdmin object for a user"""
    try:
        return TeacherAdmin.objects.get(user=user)
    except TeacherAdmin.DoesNotExist:
        return None


def is_admin(user):
    """Check if user is admin or superuser"""
    if user.is_superuser:
        return True
    teacher = get_teacher_admin(user)
    return teacher and teacher.role == "Admin"


def is_teacher(user):
    """Check if user is teacher"""
    if user.is_superuser:
        return False
    teacher = get_teacher_admin(user)
    return teacher and teacher.role == "Teacher"


@login_required
def index(request):
    """Main view - redirects based on role"""
    # Superuser gets admin view
    if request.user.is_superuser:
        return admin_schedule_management(request)
    
    teacher = get_teacher_admin(request.user)
    
    if not teacher:
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'You are not authorized to view this page.'
        })
    
    if teacher.role == "Admin":
        return admin_schedule_management(request)
    elif teacher.role == "Teacher":
        return teacher_schedule_viewer(request)
    else:
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'Invalid role.'
        })


@login_required
def admin_schedule_management(request):
    """Admin Schedule Management Page"""
    if not is_admin(request.user):
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'Admin access required.'
        })
    
    teachers = TeacherAdmin.objects.filter(role="Teacher")
    subjects = SubjectSchedule.objects.all()
    all_subjects = Subject.objects.all().values('name', 'grade', 'board', 'batch').distinct()
    
    # Get filter parameters
    filter_subject = request.GET.get('subject', '')
    filter_date_from = request.GET.get('date_from', '')
    filter_date_to = request.GET.get('date_to', '')
    
    entries = ScheduleEntry.objects.select_related('subject', 'teacher').order_by('date', 'lecture_number')
    
    if filter_subject:
        entries = entries.filter(subject__subject=filter_subject)
    if filter_date_from:
        entries = entries.filter(date__gte=filter_date_from)
    if filter_date_to:
        entries = entries.filter(date__lte=filter_date_to)
    
    entries = list(entries[:50])
    uploaded_files = list(
        UploadedSchedule.objects.select_related('uploaded_by').order_by('-uploaded_at')[:10]
    )
    parsed_imports = [parse_uploaded_schedule(uploaded_file) for uploaded_file in uploaded_files]

    context = {
        'teachers': teachers,
        'subjects': subjects,
        'all_subjects': list(all_subjects),
        'entries': entries,
        'entries_json': serialize_schedule_entries(entries),
        'parsed_imports_json': parsed_imports,
        'filter_subject': filter_subject,
        'filter_date_from': filter_date_from,
        'filter_date_to': filter_date_to,
        'is_superuser': request.user.is_superuser,
    }
    
    return render(request, 'teacherschedule/admin-management.html', context)


@login_required
def teacher_schedule_viewer(request):
    """Teacher Schedule Viewer Page"""
    if not is_teacher(request.user):
        return render(request, 'teacherschedule/notAuthorized.html', {
            'message': 'Teacher access required.'
        })
    
    teacher = get_teacher_admin(request.user)
    
    # Get filter parameters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    subject_filter = request.GET.get('subject', '')
    
    entries = ScheduleEntry.objects.filter(teacher=teacher).select_related('subject').order_by('date', 'lecture_number')
    
    if date_from:
        entries = entries.filter(date__gte=date_from)
    if date_to:
        entries = entries.filter(date__lte=date_to)
    if subject_filter:
        entries = entries.filter(subject__subject=subject_filter)
    
    # Calculate today's schedule
    today = timezone.now().date()
    today_entries = entries.filter(date=today)
    
    # Subject-wise topics count
    completed_count = entries.filter(is_completed=True).count()
    total_count = entries.count()
    completion_percent = (completed_count / total_count * 100) if total_count > 0 else 0
    
    context = {
        'teacher': teacher,
        'entries': entries[:50],
        'today_entries': today_entries,
        'completed_count': completed_count,
        'total_count': total_count,
        'completion_percent': round(completion_percent, 1),
        'date_from': date_from,
        'date_to': date_to,
        'subject_filter': subject_filter,
    }
    
    return render(request, 'teacherschedule/teacher-viewer.html', context)


@login_required
def add_schedule_entry(request):
    """Add new schedule entry"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Get or create subject
            subject, _ = SubjectSchedule.objects.get_or_create(
                subject=data.get('subject'),
                grade=data.get('grade', '10'),
                board=data.get('board', 'CBSE'),
                batch=data.get('batch', 'B1')
            )
            
            entry = ScheduleEntry.objects.create(
                date=datetime.strptime(data.get('date'), '%Y-%m-%d').date(),
                subject=subject,
                topic=data.get('topic', ''),
                chapter=data.get('chapter', ''),
                notes=data.get('notes', ''),
                duration=data.get('duration', '1'),
                lecture_number=int(data.get('lecture_number', 1)),
                teacher_id=data.get('teacher_id')
            )
            
            entry = ScheduleEntry.objects.select_related('subject', 'teacher').get(id=entry.id)
            return JsonResponse({
                'success': True,
                'entry_id': entry.id,
                'entry': serialize_schedule_entry(entry),
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def update_schedule_entry(request, entry_id):
    """Update schedule entry"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            entry = get_object_or_404(ScheduleEntry, id=entry_id)
            
            if 'topic' in data:
                entry.topic = data['topic']
            if 'chapter' in data:
                entry.chapter = data['chapter']
            if 'notes' in data:
                entry.notes = data['notes']
            if 'duration' in data:
                entry.duration = data['duration']
            if 'is_completed' in data:
                entry.is_completed = data['is_completed']
            if 'teacher_id' in data:
                entry.teacher_id = data['teacher_id']
            
            entry.save()
            entry = ScheduleEntry.objects.select_related('subject', 'teacher').get(id=entry.id)
            
            return JsonResponse({'success': True, 'entry': serialize_schedule_entry(entry)})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def delete_schedule_entry(request, entry_id):
    """Delete schedule entry"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            entry = get_object_or_404(ScheduleEntry, id=entry_id)
            entry.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def get_calendar_data(request):
    """Get schedule data for calendar view"""
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    if not month or not year:
        today = timezone.now()
        month = today.month
        year = today.year
    else:
        month = int(month)
        year = int(year)
    
    # Get all entries for the month
    start_date = datetime(year, month, 1).date()
    if month == 12:
        end_date = datetime(year + 1, 1, 1).date()
    else:
        end_date = datetime(year, month + 1, 1).date()
    
    entries = ScheduleEntry.objects.filter(
        date__gte=start_date,
        date__lt=end_date
    ).select_related('subject', 'teacher')
    
    # Filter by teacher if teacher user
    if is_teacher(request.user):
        teacher = get_teacher_admin(request.user)
        entries = entries.filter(teacher=teacher)
    
    data = []
    for entry in entries:
        data.append({
            'id': entry.id,
            'date': entry.date.strftime('%Y-%m-%d'),
            'subject': entry.subject.subject,
            'topic': entry.topic,
            'teacher': entry.teacher.name if entry.teacher else '',
            'duration': entry.duration,
            'is_completed': entry.is_completed,
        })
    
    return JsonResponse({'entries': data})


@login_required
def bulk_assign_teacher(request):
    """Bulk assign teacher to schedule entries"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            entry_ids = data.get('entry_ids', [])
            teacher_id = data.get('teacher_id')
            
            ScheduleEntry.objects.filter(id__in=entry_ids).update(teacher_id=teacher_id)
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
def export_schedule(request):
    """Export schedule to PDF/Excel"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)
    
    export_format = request.GET.get('format', 'excel')
    
    entries = ScheduleEntry.objects.select_related('subject', 'teacher').order_by('date', 'lecture_number')
    
    if export_format == 'excel':
        headers = [
            'Date',
            'Subject',
            'Grade',
            'Topic',
            'Chapter',
            'Teacher',
            'Duration',
            'Lecture #',
            'Completed',
            'Notes',
        ]
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=schedule.csv'
        writer = csv.writer(response)
        writer.writerow(headers)

        for entry in entries:
            writer.writerow([
                entry.date.strftime('%Y-%m-%d'),
                entry.subject.subject,
                entry.subject.grade,
                entry.topic,
                entry.chapter,
                entry.teacher.name if entry.teacher else '',
                entry.duration,
                entry.lecture_number,
                'Yes' if entry.is_completed else 'No',
                entry.notes,
            ])

        return response
    
    return JsonResponse({'error': 'Invalid format'}, status=400)


@login_required
def import_schedule(request):
    """Upload teacher schedule file"""
    if not is_admin(request.user):
        return JsonResponse({'error': 'Admin access required'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request'}, status=400)

    uploaded_file = request.FILES.get('schedule_file')
    if not uploaded_file:
        return JsonResponse({'error': 'Please select a file to import'}, status=400)

    file_extension = os.path.splitext(uploaded_file.name)[1].lower()
    allowed_file_types = {
        '.pdf': 'PDF',
        '.xls': 'EXCEL',
        '.xlsx': 'EXCEL',
    }

    if file_extension not in allowed_file_types:
        return JsonResponse({'error': 'Only PDF and Excel files are allowed'}, status=400)

    uploaded_schedule = UploadedSchedule.objects.create(
        file_name=uploaded_file.name,
        file_type=allowed_file_types[file_extension],
        file=uploaded_file,
        grade=request.POST.get('grade', 'All'),
        board=request.POST.get('board', 'General'),
        batch=request.POST.get('batch', 'B1'),
        uploaded_by=request.user,
    )

    return JsonResponse({
        'success': True,
        'message': f'{uploaded_file.name} imported successfully',
        'parsed_import': parse_uploaded_schedule(uploaded_schedule),
    })


@login_required
def mark_completed(request, entry_id):
    """Mark entry as completed"""
    if request.method == 'POST':
        try:
            entry = get_object_or_404(ScheduleEntry, id=entry_id)
            entry.is_completed = not entry.is_completed
            entry.save()
            return JsonResponse({'success': True, 'is_completed': entry.is_completed})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
