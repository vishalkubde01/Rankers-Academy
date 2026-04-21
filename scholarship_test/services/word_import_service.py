from html import escape
from pathlib import Path
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


DOCX_NAMESPACE = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
BLOCK_MARKERS = {'question', 'type', 'option', 'answer', 'solution', 'marks'}

TYPE_MAP = {
    'multiple_choice': 'mcq',
    'multiple choice': 'mcq',
    'integer': 'int',
    'fill_ups': 'fitb',
    'fill ups': 'fitb',
    'fillups': 'fitb',
    'true_false': 'tf',
    'true false': 'tf',
    'comprehension': 'comp',
}


class WordImportError(ValueError):
    pass


def import_questions_from_docx(uploaded_file):
    paragraphs = _extract_docx_paragraphs(uploaded_file)
    if not paragraphs:
        raise WordImportError("The Word file is empty or could not be read.")

    questions, warnings = _parse_question_blocks(paragraphs)
    if not questions:
        raise WordImportError("No questions matching the sample format were found.")

    section_name = Path(getattr(uploaded_file, 'name', 'Imported Questions')).stem.strip()
    return {
        'section_name': section_name or 'Imported Questions',
        'questions': questions,
        'warnings': warnings,
    }


def _extract_docx_paragraphs(uploaded_file):
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    try:
        with ZipFile(uploaded_file) as archive:
            document_xml = archive.read('word/document.xml')
    except KeyError as exc:
        raise WordImportError("The Word file is missing its document content.") from exc
    except BadZipFile as exc:
        raise WordImportError("Only valid .docx Word files are supported.") from exc

    try:
        root = ET.fromstring(document_xml)
    except ET.ParseError as exc:
        raise WordImportError("The Word file could not be parsed.") from exc

    paragraphs = []
    for para in root.findall('.//w:p', DOCX_NAMESPACE):
        text_parts = []
        for text_node in para.findall('.//w:t', DOCX_NAMESPACE):
            text_parts.append(text_node.text or '')
        text = ''.join(text_parts).strip()
        if text:
            paragraphs.append(text)

    return paragraphs


def _parse_question_blocks(lines):
    index = 0
    questions = []
    warnings = []

    while index < len(lines):
        marker = _normalize_marker(lines[index])
        if marker != 'question':
            index += 1
            continue

        question, index, question_warnings = _parse_single_question(lines, index)
        questions.append(question)
        warnings.extend(question_warnings)

    return questions, warnings


def _parse_single_question(lines, index):
    warnings = []

    index += 1
    question_lines, index = _collect_until_marker(lines, index)

    if index >= len(lines) or _normalize_marker(lines[index]) != 'type':
        raise WordImportError("Each question block must contain a Type field.")

    index += 1
    type_lines, index = _collect_until_marker(lines, index)
    raw_type = ' '.join(type_lines).strip()
    question_type = TYPE_MAP.get(_normalize_type(raw_type))
    if not question_type:
        raise WordImportError(f"Unsupported question type: {raw_type or 'blank'}.")

    if question_type == 'mcq':
        question, index = _parse_multiple_choice(lines, index, question_lines)
    elif question_type == 'fitb':
        question, index = _parse_fill_ups(lines, index, question_lines)
    elif question_type == 'tf':
        question, index = _parse_answer_question(lines, index, question_lines, 'tf')
    elif question_type == 'int':
        question, index = _parse_answer_question(lines, index, question_lines, 'int')
    elif question_type == 'comp':
        question, index, comp_warnings = _parse_comprehension(lines, index, question_lines)
        warnings.extend(comp_warnings)
    else:
        raise WordImportError(f"Unsupported question type: {raw_type or 'blank'}.")

    return question, index, warnings


def _parse_multiple_choice(lines, index, question_lines):
    options = []
    correct_indexes = []

    while index < len(lines) and _normalize_marker(lines[index]) == 'option':
        index += 1
        option_lines, index = _collect_until_marker(lines, index)
        if not option_lines:
            continue

        status = _normalize_status(option_lines[-1])
        if status in {'correct', 'incorrect'}:
            option_text = '\n'.join(option_lines[:-1]).strip()
        else:
            status = 'incorrect'
            option_text = '\n'.join(option_lines).strip()

        options.append(option_text)
        if status == 'correct':
            correct_indexes.append(len(options) - 1)

    _, index = _consume_optional_solution(lines, index)
    pos_marks, neg_marks, index = _consume_marks(lines, index)

    return (
        {
            'type': 'mcq',
            'text': _lines_to_html(question_lines),
            'difficulty': 'Medium',
            'pos_marks': pos_marks,
            'neg_marks': neg_marks,
            'neg_unattempted': 0,
            'tags': [],
            'options': options,
            'correct_options': correct_indexes,
            'multi_select': len(correct_indexes) > 1,
        },
        index,
    )


def _parse_fill_ups(lines, index, question_lines):
    accepted_answers = []

    while index < len(lines) and _normalize_marker(lines[index]) == 'option':
        index += 1
        option_lines, index = _collect_until_marker(lines, index)
        answer_value = '\n'.join(option_lines).strip()
        if answer_value:
            accepted_answers.append(answer_value)

    _, index = _consume_optional_solution(lines, index)
    pos_marks, neg_marks, index = _consume_marks(lines, index)

    return (
        {
            'type': 'fitb',
            'text': _lines_to_html(question_lines),
            'difficulty': 'Medium',
            'pos_marks': pos_marks,
            'neg_marks': neg_marks,
            'neg_unattempted': 0,
            'tags': [],
            'correct_answer': ' | '.join(accepted_answers),
        },
        index,
    )


def _parse_answer_question(lines, index, question_lines, question_type):
    answer_value = ''

    if index < len(lines) and _normalize_marker(lines[index]) == 'answer':
        index += 1
        answer_lines, index = _collect_until_marker(lines, index)
        answer_value = '\n'.join(answer_lines).strip()

    _, index = _consume_optional_solution(lines, index)
    pos_marks, neg_marks, index = _consume_marks(lines, index)

    return (
        {
            'type': question_type,
            'text': _lines_to_html(question_lines),
            'difficulty': 'Medium',
            'pos_marks': pos_marks,
            'neg_marks': neg_marks,
            'neg_unattempted': 0,
            'tags': [],
            'correct_answer': answer_value,
        },
        index,
    )


def _parse_comprehension(lines, index, question_lines):
    warnings = []
    nested_questions = []

    while index < len(lines):
        marker = _normalize_marker(lines[index])
        if marker != 'question':
            break

        nested_question, index, nested_warnings = _parse_single_question(lines, index)
        nested_questions.append(_format_comprehension_subquestion(nested_question, len(nested_questions) + 1))
        warnings.extend(nested_warnings)

    title = question_lines[0] if question_lines else 'Comprehension'
    passage_lines = question_lines[1:] if len(question_lines) > 1 else question_lines

    if not nested_questions:
        warnings.append("A comprehension passage was found without any nested questions.")

    return (
        {
            'type': 'comp',
            'text': _lines_to_html([title]),
            'difficulty': 'Medium',
            'pos_marks': 0,
            'neg_marks': 0,
            'neg_unattempted': 0,
            'tags': [],
            'passage': _lines_to_html(passage_lines),
            'sub_questions': nested_questions,
        },
        index,
        warnings,
    )


def _format_comprehension_subquestion(question, number):
    type_label = {
        'mcq': 'Multiple Choice',
        'fitb': 'Fill In The Blanks',
        'tf': 'True / False',
        'int': 'Integer',
        'comp': 'Comprehension',
    }.get(question.get('type'), 'Question')

    parts = [f"{number}. [{type_label}] {_html_to_text(question.get('text', ''))}"]

    if question.get('type') == 'mcq':
        options = question.get('options', [])
        correct_indexes = set(question.get('correct_options', []))
        for option_index, option_text in enumerate(options):
            marker = ' (Correct)' if option_index in correct_indexes else ''
            parts.append(f"Option {option_index + 1}: {option_text}{marker}")
    elif question.get('correct_answer'):
        parts.append(f"Answer: {question.get('correct_answer')}")

    parts.append(
        f"Marks: +{question.get('pos_marks', 0)} / -{question.get('neg_marks', 0)}"
    )
    return '\n'.join(parts)


def _consume_optional_solution(lines, index):
    if index < len(lines) and _normalize_marker(lines[index]) == 'solution':
        index += 1
        return _collect_until_marker(lines, index)
    return [], index


def _consume_marks(lines, index):
    if index >= len(lines) or _normalize_marker(lines[index]) != 'marks':
        return 0, 0, index

    index += 1
    mark_lines, index = _collect_until_marker(lines, index)
    pos_marks = _to_number(mark_lines[0]) if len(mark_lines) >= 1 else 0
    neg_marks = _to_number(mark_lines[1]) if len(mark_lines) >= 2 else 0
    return pos_marks, neg_marks, index


def _collect_until_marker(lines, index):
    collected = []
    while index < len(lines) and _normalize_marker(lines[index]) not in BLOCK_MARKERS:
        collected.append(lines[index].strip())
        index += 1
    return collected, index


def _normalize_marker(value):
    return str(value or '').strip().lower()


def _normalize_type(value):
    return str(value or '').strip().lower().replace('-', '_')


def _normalize_status(value):
    return str(value or '').strip().lower()


def _to_number(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _lines_to_html(lines):
    cleaned_lines = [escape(str(line).strip()) for line in lines if str(line).strip()]
    return '<br>'.join(cleaned_lines)


def _html_to_text(value):
    return (
        str(value or '')
        .replace('<br>', '\n')
        .replace('<br/>', '\n')
        .replace('<br />', '\n')
    )
