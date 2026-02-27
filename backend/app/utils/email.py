"""
Email service for sending reports and notifications
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import parseaddr
from typing import Optional
from io import BytesIO

from app.core.config import settings


def _sanitize_email_address(value: str) -> str:
    if not value:
        raise ValueError("Empty email address")
    _, addr = parseaddr(value)
    addr = addr.strip().rstrip("\\")
    if not addr or "@" not in addr or " " in addr or "\\" in addr:
        raise ValueError(f"Invalid email address: {value}")
    return addr


async def send_email_with_attachment(
    to_email: str,
    subject: str,
    body_html: str,
    attachment_data: Optional[BytesIO] = None,
    attachment_filename: Optional[str] = None
) -> bool:
    """
    Send email with optional PDF attachment
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body_html: HTML body content
        attachment_data: PDF file as BytesIO
        attachment_filename: Name for the attachment
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        print("⚠️  Email not configured. Skipping email send.")
        return False
    
    try:
        # Create message
        sender_email = _sanitize_email_address(settings.SMTP_FROM_EMAIL or settings.SMTP_USER)
        recipient_email = _sanitize_email_address(to_email)
        msg = MIMEMultipart()
        msg['From'] = f"{settings.SMTP_FROM_NAME} <{sender_email}>"
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        # Add HTML body
        msg.attach(MIMEText(body_html, 'html'))
        
        # Add attachment if provided
        if attachment_data and attachment_filename:
            attachment_data.seek(0)
            pdf_attachment = MIMEApplication(attachment_data.read(), _subtype='pdf')
            pdf_attachment.add_header('Content-Disposition', 'attachment', 
                                     filename=attachment_filename)
            msg.attach(pdf_attachment)
        
        # Send email
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email sent to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


def generate_student_email_body(student_name: str, exam_title: str, 
                                 total_score: float, max_score: float,
                                 integrity_score: float) -> str:
    """Generate HTML email body for student report"""
    percentage = (total_score / max_score * 100) if max_score > 0 else 0
    
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #1976d2; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .score-box {{ background-color: #e3f2fd; border-left: 4px solid #1976d2; padding: 15px; margin: 20px 0; }}
            .footer {{ background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Exam Results Available</h1>
        </div>
        <div class="content">
            <p>Dear {student_name},</p>
            
            <p>Your results for <strong>{exam_title}</strong> are now available.</p>
            
            <div class="score-box">
                <h3>Your Performance:</h3>
                <ul>
                    <li><strong>Total Score:</strong> {total_score:.1f} / {max_score:.1f} ({percentage:.1f}%)</li>
                    <li><strong>Integrity Score:</strong> {integrity_score:.1f}%</li>
                </ul>
            </div>
            
            <p>Please find your detailed performance report attached to this email.</p>
            
            <p>The report includes:</p>
            <ul>
                <li>Question-wise breakdown</li>
                <li>Performance analysis</li>
                <li>Proctoring summary</li>
                <li>Detailed charts and visualizations</li>
            </ul>
            
            <p>If you have any questions about your results, please contact your instructor.</p>
            
            <p>Best regards,<br>
            <strong>Quatarly Team</strong></p>
        </div>
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
        </div>
    </body>
    </html>
    """


def generate_professor_email_body(professor_name: str, exam_title: str, 
                                   total_students: int, avg_score: float,
                                   avg_integrity: float) -> str:
    """Generate HTML email body for professor report"""
    return f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #283593; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .stats-box {{ background-color: #f3e5f5; border-left: 4px solid #7b1fa2; padding: 15px; margin: 20px 0; }}
            .footer {{ background-color: #f5f5f5; padding: 15px; text-align: center; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Exam Analysis Report</h1>
        </div>
        <div class="content">
            <p>Dear {professor_name},</p>
            
            <p>The analysis report for <strong>{exam_title}</strong> is ready.</p>
            
            <div class="stats-box">
                <h3>Exam Statistics:</h3>
                <ul>
                    <li><strong>Total Students:</strong> {total_students}</li>
                    <li><strong>Average Score:</strong> {avg_score:.2f}</li>
                    <li><strong>Average Integrity:</strong> {avg_integrity:.1f}%</li>
                </ul>
            </div>
            
            <p>Please find the comprehensive exam analysis report attached to this email.</p>
            
            <p>The report includes:</p>
            <ul>
                <li>Student rankings</li>
                <li>Score distribution</li>
                <li>Integrity metrics</li>
                <li>Performance analytics</li>
            </ul>
            
            <p>Best regards,<br>
            <strong>Quatarly Team</strong></p>
        </div>
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
        </div>
    </body>
    </html>
    """
