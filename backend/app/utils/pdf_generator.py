"""
PDF Report Generator for Exam Results - Quatarly
Generates comprehensive performance reports with charts and analysis
"""
from datetime import datetime
from io import BytesIO
from typing import Any

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image as RLImage
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


def create_pie_chart(data: dict[str, int], title: str) -> BytesIO:
    """Create a pie chart and return as BytesIO"""
    fig, ax = plt.subplots(figsize=(6, 4))
    
    if data and sum(data.values()) > 0:
        ax.pie(data.values(), labels=data.keys(), autopct='%1.1f%%', startangle=90)
        ax.set_title(title)
    else:
        ax.text(0.5, 0.5, 'No Data', ha='center', va='center', fontsize=16)
        ax.set_title(title)
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close()
    buffer.seek(0)
    return buffer


def create_bar_chart(labels: list[str], values: list[float], title: str, ylabel: str) -> BytesIO:
    """Create a bar chart and return as BytesIO"""
    fig, ax = plt.subplots(figsize=(8, 4))
    
    if labels and values:
        ax.bar(labels, values, color='steelblue')
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xlabel('Questions')
        plt.xticks(rotation=45, ha='right')
    else:
        ax.text(0.5, 0.5, 'No Data', ha='center', va='center', fontsize=16)
        ax.set_title(title)
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close()
    buffer.seek(0)
    return buffer


def create_line_chart(labels: list[str], values: list[float], title: str, ylabel: str) -> BytesIO:
    fig, ax = plt.subplots(figsize=(8, 4))
    if labels and values:
        ax.plot(labels, values, marker='o', linewidth=2, color='steelblue')
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xlabel('Questions')
        plt.xticks(rotation=45, ha='right')
    else:
        ax.text(0.5, 0.5, 'No Data', ha='center', va='center', fontsize=16)
        ax.set_title(title)
    buffer = BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close()
    buffer.seek(0)
    return buffer


def create_timeline_chart(violations: list[dict], title: str) -> BytesIO:
    """Create a timeline chart for violations"""
    fig, ax = plt.subplots(figsize=(10, 4))
    
    if violations:
        # Group violations by type
        violation_types = {}
        for v in violations:
            vtype = v['violation_type']
            if vtype not in violation_types:
                violation_types[vtype] = []
            # Parse timestamp
            timestamp = datetime.fromisoformat(v['created_at'].replace('Z', '+00:00'))
            violation_types[vtype].append(timestamp)
        
        # Plot each violation type
        colors_list = ['red', 'orange', 'yellow', 'purple', 'pink', 'brown']
        for idx, (vtype, timestamps) in enumerate(violation_types.items()):
            y_values = [idx] * len(timestamps)
            ax.scatter(timestamps, y_values, label=vtype, s=100, 
                      color=colors_list[idx % len(colors_list)])
        
        ax.set_yticks(range(len(violation_types)))
        ax.set_yticklabels(list(violation_types.keys()))
        ax.set_xlabel('Time')
        ax.set_title(title)
        ax.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, 'No Violations', ha='center', va='center', fontsize=16)
        ax.set_title(title)
    
    buffer = BytesIO()
    plt.savefig(buffer, format='png', bbox_inches='tight', dpi=100)
    plt.close()
    buffer.seek(0)
    return buffer


def generate_student_report(
    student_name: str,
    exam_title: str,
    session_data: dict[str, Any],
    responses: list[dict],
    violations: list[dict],
    topic_analytics: list[dict] | None = None,
    question_analytics: list[dict] | None = None,
    comparative_analytics: dict[str, Any] | None = None,
    time_analytics: dict[str, Any] | None = None,
) -> BytesIO:
    """
    Generate comprehensive PDF report for a student
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a237e'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#283593'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Cover Page
    elements.append(Spacer(1, 2*inch))
    elements.append(Paragraph("QUATARLY", title_style))
    elements.append(Paragraph("EXAM PERFORMANCE REPORT", heading_style))
    elements.append(Spacer(1, 0.5*inch))
    
    cover_data = [
        ['Student Name:', student_name],
        ['Exam Title:', exam_title],
        ['Date:', datetime.now().strftime('%B %d, %Y')],
        ['Status:', session_data.get('status', 'N/A').upper()],
    ]
    
    cover_table = Table(cover_data, colWidths=[2*inch, 4*inch])
    cover_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(cover_table)
    
    elements.append(Spacer(1, 0.5*inch))
    
    total_score = session_data.get('total_score', 0)
    max_score = session_data.get('total_marks')
    if max_score is None:
        max_score = sum(r['marks'] for r in responses) if responses else 0
    percentage = (total_score / max_score * 100) if max_score > 0 else 0
    integrity_score = session_data.get('integrity_score', 100)
    
    score_data = [
        ['TOTAL SCORE', f"{total_score:.1f} / {max_score:.1f}"],
        ['PERCENTAGE', f"{percentage:.1f}%"],
        ['INTEGRITY SCORE', f"{integrity_score:.1f}%"],
    ]
    
    score_table = Table(score_data, colWidths=[3*inch, 3*inch])
    score_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 16),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#e3f2fd')),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#1976d2')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#90caf9')),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
    ]))
    elements.append(score_table)
    
    elements.append(PageBreak())
    
    comparative = comparative_analytics or session_data.get("comparative") or {}
    time_metrics = time_analytics or session_data.get("time_analytics") or {}

    elements.append(Paragraph("Performance Summary", heading_style))
    elements.append(Spacer(1, 0.2*inch))

    summary_rows = [
        ["Score", f"{total_score:.1f} / {max_score:.1f}"],
        ["Percentage", f"{percentage:.1f}%"],
        ["Class Average", f"{comparative.get('class_average', '—')}"],
        ["Percentile", f"{comparative.get('percentile', '—')}"],
        ["Rank", f"{comparative.get('rank', '—')} / {comparative.get('total_students', '—')}"],
        ["Integrity", f"{integrity_score:.1f}%"],
        ["Total Time", f"{time_metrics.get('total_time_minutes', 0)} min"],
        ["Avg Time / Question", f"{time_metrics.get('average_time_per_question', 0)} sec"],
    ]
    summary_table = Table(summary_rows, colWidths=[2.5*inch, 3.5*inch])
    summary_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f7fa')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d0d7de')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Topic-wise Analysis
    if topic_analytics:
        elements.append(Paragraph("Topic-wise Accuracy", heading_style))
        elements.append(Spacer(1, 0.2*inch))

        topic_rows = [["Topic", "Accuracy", "Score", "Max", "Attempts"]]
        for item in topic_analytics:
            topic_rows.append([
                item.get("topic", "General"),
                f"{item.get('accuracy_pct', 0)}%",
                f"{item.get('scored', 0)}",
                f"{item.get('possible', 0)}",
                str(item.get("attempts", 0)),
            ])

        topic_table = Table(topic_rows, colWidths=[2*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        topic_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(topic_table)

        labels = [t.get("topic", "General") for t in topic_analytics]
        values = [t.get("accuracy_pct", 0) for t in topic_analytics]
        chart_buffer = create_bar_chart(labels, values, "Topic Accuracy", "Accuracy (%)")
        elements.append(Spacer(1, 0.2*inch))
        elements.append(RLImage(chart_buffer, width=6*inch, height=3*inch))
        elements.append(PageBreak())

    # Question-wise Analysis
    elements.append(Paragraph("Question-wise Performance", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    if responses:
        question_data = [['Q#', 'Your Answer', 'Score', 'Max Marks', 'Status']]
        
        for idx, response in enumerate(responses, 1):
            score = response.get('score', 0) or 0
            marks = response.get('marks', 0)
            answer = response.get('answer', 'Not answered')
            
            # Truncate long answers
            if len(answer) > 50:
                answer = answer[:47] + '...'
            
            status = '✓' if score >= marks * 0.7 else '✗'
            
            question_data.append([
                str(idx),
                answer,
                f"{score:.1f}",
                f"{marks:.1f}",
                status
            ])
        
        question_table = Table(question_data, colWidths=[0.5*inch, 3*inch, 0.8*inch, 1*inch, 0.7*inch])
        question_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (1, 1), (1, -1), 'LEFT'),
        ]))
        elements.append(question_table)

    if question_analytics:
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("Difficulty & Timing Insights", heading_style))
        elements.append(Spacer(1, 0.2*inch))

        qa_rows = [["Q#", "Difficulty", "Class Avg", "Your Score", "Avg Time", "Your Time"]]
        for idx, item in enumerate(question_analytics, 1):
            qa_rows.append([
                str(idx),
                item.get("difficulty_category", "—"),
                str(item.get("average_score", "—")),
                str(item.get("student_score", "—")),
                str(item.get("average_time_seconds", "—")),
                str(item.get("student_time_seconds", "—")),
            ])
        qa_table = Table(qa_rows, colWidths=[0.5*inch, 1.2*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        qa_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ]))
        elements.append(qa_table)
    
    elements.append(PageBreak())
    
    # Performance Charts
    elements.append(Paragraph("Performance Visualization", heading_style))
    elements.append(Spacer(1, 0.2*inch))

    if responses:
        labels = [f"Q{i+1}" for i in range(len(responses))]
        scores = [r.get('score', 0) or 0 for r in responses]
        score_chart = create_bar_chart(labels, scores, "Score per Question", "Score")
        elements.append(RLImage(score_chart, width=6*inch, height=3*inch))

    if responses:
        times = [r.get('time_spent_seconds', 0) or 0 for r in responses]
        time_chart = create_line_chart(labels, times, "Time per Question", "Seconds")
        elements.append(Spacer(1, 0.2*inch))
        elements.append(RLImage(time_chart, width=6*inch, height=3*inch))
    
    elements.append(Spacer(1, 0.3*inch))
    
    if time_metrics:
        elements.append(Spacer(1, 0.3*inch))
        elements.append(Paragraph("Pacing Analysis", heading_style))
        elements.append(Spacer(1, 0.2*inch))
        pacing_rows = [
            ["Total Time (min)", time_metrics.get("total_time_minutes", 0)],
            ["Average per Question (sec)", time_metrics.get("average_time_per_question", 0)],
            ["Fastest Question (sec)", time_metrics.get("fastest_question_time", 0)],
            ["Slowest Question (sec)", time_metrics.get("slowest_question_time", 0)],
        ]
        pacing_table = Table(pacing_rows, colWidths=[3*inch, 3*inch])
        pacing_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f7fa')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#d0d7de')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
        ]))
        elements.append(pacing_table)

    # Proctoring Report
    elements.append(PageBreak())
    elements.append(Paragraph("Proctoring & Integrity Report", heading_style))
    elements.append(Spacer(1, 0.2*inch))
    
    violation_summary = session_data.get('violation_summary', {})
    
    if violation_summary and sum(violation_summary.values()) > 0:
        # Violation pie chart
        pie_buffer = create_pie_chart(violation_summary, "Violation Distribution")
        pie_img = RLImage(pie_buffer, width=5*inch, height=3*inch)
        elements.append(pie_img)
        elements.append(Spacer(1, 0.3*inch))
        
        # Violation timeline
        if violations:
            timeline_buffer = create_timeline_chart(violations, "Violation Timeline")
            timeline_img = RLImage(timeline_buffer, width=6.5*inch, height=3*inch)
            elements.append(timeline_img)
        
        elements.append(Spacer(1, 0.3*inch))
        
        # Violation details table
        violation_data = [['Violation Type', 'Count', 'Severity']]
        severity_map = {
            'phone_detected': 'High',
            'multiple_faces': 'High',
            'raf_tab_switch': 'Medium',
            'gaze_away': 'Medium',
            'speech_detected': 'Low',
            'no_mouse': 'Low'
        }
        
        for vtype, count in violation_summary.items():
            violation_data.append([
                vtype.replace('_', ' ').title(),
                str(count),
                severity_map.get(vtype, 'Medium')
            ])
        
        violation_table = Table(violation_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        violation_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(violation_table)
    else:
        elements.append(Paragraph(
            "✓ No violations detected. Excellent exam conduct!",
            styles['BodyText']
        ))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generate_professor_report(
    exam_title: str,
    sessions: list[dict],
    exam_data: dict
) -> BytesIO:
    """
    Generate comprehensive PDF report for professor (exam-wide analysis)
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                           rightMargin=72, leftMargin=72,
                           topMargin=72, bottomMargin=18)
    
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a237e'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#283593'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Cover Page
    elements.append(Spacer(1, 2*inch))
    elements.append(Paragraph("QUATARLY", title_style))
    elements.append(Paragraph("EXAM ANALYSIS REPORT", heading_style))
    elements.append(Paragraph("(Professor View)", styles['Heading3']))
    elements.append(Spacer(1, 0.5*inch))
    
    cover_data = [
        ['Exam Title:', exam_title],
        ['Total Students:', str(len(sessions))],
        ['Date Generated:', datetime.now().strftime('%B %d, %Y %H:%M')],
    ]
    
    cover_table = Table(cover_data, colWidths=[2*inch, 4*inch])
    cover_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(cover_table)
    
    elements.append(PageBreak())
    
    # Statistics
    if sessions:
        scores = [s.get('total_score', 0) or 0 for s in sessions]
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score_val = max(scores) if scores else 0
        min_score_val = min(scores) if scores else 0
        
        integrity_scores = [s.get('integrity_score', 100) or 100 for s in sessions]
        avg_integrity = sum(integrity_scores) / len(integrity_scores) if integrity_scores else 100
        
        elements.append(Paragraph("Exam Statistics", heading_style))
        
        stats_data = [
            ['Metric', 'Value'],
            ['Average Score', f"{avg_score:.2f}"],
            ['Highest Score', f"{max_score_val:.2f}"],
            ['Lowest Score', f"{min_score_val:.2f}"],
            ['Average Integrity', f"{avg_integrity:.2f}%"],
            ['Completion Rate', f"{len([s for s in sessions if s.get('status') == 'completed'])/len(sessions)*100:.1f}%"],
        ]
        
        stats_table = Table(stats_data, colWidths=[3*inch, 2*inch])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 1), (-1, -1), colors.lightblue),
        ]))
        elements.append(stats_table)
        
        elements.append(Spacer(1, 0.5*inch))
        
        # Student Rankings
        elements.append(Paragraph("Student Rankings", heading_style))
        
        ranking_data = [['Rank', 'Student', 'Score', 'Integrity']]
        sorted_sessions = sorted(sessions, key=lambda x: x.get('total_score', 0) or 0, reverse=True)
        
        for idx, session in enumerate(sorted_sessions[:10], 1):  # Top 10
            ranking_data.append([
                str(idx),
                session.get('student_name', 'Unknown'),
                f"{session.get('total_score', 0):.1f}",
                f"{session.get('integrity_score', 100):.1f}%"
            ])
        
        ranking_table = Table(ranking_data, colWidths=[0.7*inch, 3*inch, 1.3*inch, 1.5*inch])
        ranking_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ]))
        elements.append(ranking_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer
