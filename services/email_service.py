# services/email_service.py
"""
Email Service for the AITA platform.

Handles sending emails using SMTP for notifications, account activation, and enrollment confirmations.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from logger import logger
from settings import settings


class EmailService:
    """Service for sending emails via SMTP."""
    
    def __init__(self):
        """Initialize email service with SMTP configuration."""
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.sender_email = settings.SMTP_SENDER_EMAIL
        self.sender_name = settings.SMTP_SENDER_NAME
        self.frontend_url = settings.FRONTEND_URL
        self.templates_dir = Path(__file__).parent.parent / "email_template"
        
    def _load_template(self, template_name: str) -> str:
        """Load an email template file."""
        template_path = self.templates_dir / template_name
        if not template_path.exists():
            logger.error(f"Email template not found: {template_path}")
            return ""
        
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def _render_template(
        self,
        template_name: str,
        replacements: Dict[str, str]
    ) -> str:
        """
        Load and render an email template with replacements.
        
        Args:
            template_name: Name of the template file (e.g., "03_account_activation.html")
            replacements: Dictionary of placeholder replacements
            
        Returns:
            Rendered HTML email content
        """
        # Load header and footer
        header = self._load_template("01_email_header.html")
        footer = self._load_template("02_email_footer.html")
        
        # Load main template
        template = self._load_template(template_name)
        if not template:
            return ""
        
        # Replace placeholders
        content = template
        for key, value in replacements.items():
            content = content.replace(f"[{key}]", str(value))
            content = content.replace(f"{{{key}}}", str(value))
        
        # Replace header and footer placeholders
        content = content.replace("{EmailHeader}", header)
        content = content.replace("{EmailFooter}", footer)
        
        return content
    
    def _send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None
    ) -> bool:
        """
        Send an email via SMTP.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            to_name: Optional recipient name
            
        Returns:
            True if email sent successfully, False otherwise
        """
        if not all([self.smtp_host, self.smtp_port, self.sender_email]):
            logger.warning("SMTP not configured, skipping email send")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.sender_name} <{self.sender_email}>"
            msg["To"] = to_email
            
            # Add HTML content
            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.smtp_user and self.smtp_password:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                
                server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def send_activation_email(
        self,
        to_email: str,
        activation_link: str,
        to_name: Optional[str] = None
    ) -> bool:
        """
        Send account activation email with password setup link.
        
        Args:
            to_email: Recipient email address
            activation_link: One-time activation link with token
            to_name: Optional recipient name
            
        Returns:
            True if email sent successfully
        """
        replacements = {
            "ACTIVATION_LINK": activation_link,
        }
        
        html_content = self._render_template("03_account_activation.html", replacements)
        
        if not html_content:
            logger.error("Failed to render activation email template")
            return False
        
        subject = "Activate Your AITA Platform Account"
        return self._send_email(to_email, subject, html_content, to_name)
    
    def send_enrollment_confirmation(
        self,
        to_email: str,
        student_name: str,
        course_name: str,
        teacher_name: Optional[str] = None,
        dashboard_link: Optional[str] = None
    ) -> bool:
        """
        Send enrollment confirmation email to student.
        
        Args:
            to_email: Student email address
            student_name: Student's full name
            course_name: Course name
            teacher_name: Teacher's name (optional)
            dashboard_link: Link to student dashboard (optional)
            
        Returns:
            True if email sent successfully
        """
        dashboard_link = dashboard_link or f"{self.frontend_url}/student/dashboard"
        
        replacements = {
            "Student Name": student_name,
            "Course Name": course_name,
            "Teacher Name": teacher_name or "Your instructor",
            "DASHBOARD_LINK": dashboard_link,
        }
        
        html_content = self._render_template("05_enrollment_confirmation.html", replacements)
        
        if not html_content:
            logger.error("Failed to render enrollment confirmation email template")
            return False
        
        subject = f"You've been enrolled in {course_name}"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_lecture_published_notification(
        self,
        to_email: str,
        student_name: str,
        lecture_title: str,
        course_name: str,
        teacher_name: str,
        lecture_link: Optional[str] = None,
        published_date: Optional[str] = None
    ) -> bool:
        """
        Send notification email when a new lecture is published.
        
        Args:
            to_email: Student email address
            student_name: Student's name
            lecture_title: Title of the published lecture
            course_name: Course name
            teacher_name: Teacher's name
            lecture_link: Link to the lecture (optional)
            published_date: Publication date (optional)
            
        Returns:
            True if email sent successfully
        """
        lecture_link = lecture_link or f"{self.frontend_url}/student/lectures"
        published_date = published_date or datetime.utcnow().strftime("%B %d, %Y")
        
        replacements = {
            "Teacher Name": teacher_name,
            "Course Name": course_name,
            "Lecture Title": lecture_title,
            "Date": published_date,
            "LECTURE_LINK": lecture_link,
        }
        
        html_content = self._render_template("06_new_lecture_published.html", replacements)
        
        if not html_content:
            logger.error("Failed to render lecture published email template")
            return False
        
        subject = f"New Lecture Available: {lecture_title}"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_assignment_notification(
        self,
        to_email: str,
        student_name: str,
        assignment_title: str,
        course_name: str,
        teacher_name: str,
        due_date: Optional[str] = None,
        max_points: Optional[int] = None,
        assignment_link: Optional[str] = None,
        is_individual: bool = True
    ) -> bool:
        """
        Send notification email when a new assignment/quiz is published.
        
        Args:
            to_email: Student email address
            student_name: Student's name
            assignment_title: Assignment/quiz title
            course_name: Course name
            teacher_name: Teacher's name
            due_date: Due date (optional)
            max_points: Maximum points (optional)
            assignment_link: Link to assignment (optional)
            is_individual: True for individual assignment, False for class assignment
            
        Returns:
            True if email sent successfully
        """
        assignment_link = assignment_link or f"{self.frontend_url}/student/assessments"
        
        template_name = "07_new_assignment_individual.html" if is_individual else "09_new_assignment_class.html"
        
        replacements = {
            "Teacher Name": teacher_name,
            "Course Name": course_name,
            "Assignment/Quiz Title": assignment_title,
            "Due Date": due_date or "Not specified",
            "Max Points": str(max_points) if max_points else "Not specified",
            "ASSIGNMENT_LINK": assignment_link,
        }
        
        html_content = self._render_template(template_name, replacements)
        
        if not html_content:
            logger.error(f"Failed to render assignment email template: {template_name}")
            return False
        
        subject = f"New Assignment: {assignment_title}"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_result_published_notification(
        self,
        to_email: str,
        student_name: str,
        quiz_title: str,
        score: float,
        max_score: float,
        percentage: float,
        status: str,
        result_link: Optional[str] = None
    ) -> bool:
        """
        Send notification email when quiz results are published.
        
        Args:
            to_email: Student email address
            student_name: Student's name
            quiz_title: Quiz title
            score: Student's score
            max_score: Maximum possible score
            percentage: Score percentage
            status: Passed/Failed/Reviewed
            result_link: Link to results (optional)
            
        Returns:
            True if email sent successfully
        """
        result_link = result_link or f"{self.frontend_url}/student/assessments"
        
        replacements = {
            "Quiz/Assignment Title": quiz_title,
            "Your Score": f"{score:.1f}",
            "Max Score": f"{max_score:.1f}",
            "Percentage": f"{percentage:.1f}",
            "Passed / Failed / Reviewed": status,
            "RESULT_LINK": result_link,
        }
        
        html_content = self._render_template("08_result_published.html", replacements)
        
        if not html_content:
            logger.error("Failed to render result published email template")
            return False
        
        subject = f"Your Result: {quiz_title}"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_quiz_submitted_notification(
        self,
        to_email: str,
        teacher_name: str,
        student_name: str,
        quiz_title: str,
        course_name: str,
        submission_date: str,
        assessment_link: Optional[str] = None
    ) -> bool:
        """Send notification email to teacher when a student submits a quiz."""
        assessment_link = assessment_link or f"{self.frontend_url}/teacher/assessments"
        
        replacements = {
            "Student Name": student_name,
            "Quiz Title": quiz_title,
            "Course Name": course_name,
            "Submission Date": submission_date,
            "ASSESSMENT_LINK": assessment_link,
        }
        
        html_content = self._render_template("10_quiz_submitted.html", replacements)
        
        if not html_content:
            logger.error("Failed to render quiz submitted email template")
            return False
        
        subject = f"New Quiz Submission: {quiz_title}"
        return self._send_email(to_email, subject, html_content, teacher_name)
    
    def send_low_quiz_score_notification(
        self,
        to_email: str,
        teacher_name: str,
        student_name: str,
        quiz_title: str,
        course_name: str,
        score_percentage: float,
        assessment_link: Optional[str] = None
    ) -> bool:
        """Send notification email to teacher when a student scores low on a quiz."""
        assessment_link = assessment_link or f"{self.frontend_url}/teacher/assessments"
        
        replacements = {
            "Student Name": student_name,
            "Quiz Title": quiz_title,
            "Course Name": course_name,
            "Score": f"{score_percentage:.0f}",
            "ASSESSMENT_LINK": assessment_link,
        }
        
        html_content = self._render_template("11_low_quiz_score.html", replacements)
        
        if not html_content:
            logger.error("Failed to render low quiz score email template")
            return False
        
        subject = f"⚠️ Low Score Alert: {student_name} - {quiz_title}"
        return self._send_email(to_email, subject, html_content, teacher_name)
    
    def send_result_request_notification(
        self,
        to_email: str,
        teacher_name: str,
        student_name: str,
        quiz_title: str,
        course_name: str,
        request_date: str,
        result_request_link: Optional[str] = None
    ) -> bool:
        """Send notification email to teacher when a student requests to view results."""
        result_request_link = result_request_link or f"{self.frontend_url}/teacher/result-requests"
        
        replacements = {
            "Student Name": student_name,
            "Quiz Title": quiz_title,
            "Course Name": course_name,
            "Request Date": request_date,
            "RESULT_REQUEST_LINK": result_request_link,
        }
        
        html_content = self._render_template("12_result_request.html", replacements)
        
        if not html_content:
            logger.error("Failed to render result request email template")
            return False
        
        subject = f"Result View Request: {quiz_title}"
        return self._send_email(to_email, subject, html_content, teacher_name)
    
    def send_result_approved_notification(
        self,
        to_email: str,
        student_name: str,
        quiz_title: str,
        course_name: str,
        teacher_name: str,
        result_link: Optional[str] = None
    ) -> bool:
        """Send notification email to student when their result request is approved."""
        result_link = result_link or f"{self.frontend_url}/student/assessments"
        
        replacements = {
            "Quiz Title": quiz_title,
            "Course Name": course_name,
            "Teacher Name": teacher_name,
            "RESULT_LINK": result_link,
        }
        
        html_content = self._render_template("13_result_approved.html", replacements)
        
        if not html_content:
            logger.error("Failed to render result approved email template")
            return False
        
        subject = f"Result Request Approved: {quiz_title}"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_result_rejected_notification(
        self,
        to_email: str,
        student_name: str,
        quiz_title: str,
        course_name: str,
        teacher_name: str,
        reason: Optional[str] = None,
        assessment_link: Optional[str] = None
    ) -> bool:
        """Send notification email to student when their result request is rejected."""
        assessment_link = assessment_link or f"{self.frontend_url}/student/assessments"
        
        replacements = {
            "Quiz Title": quiz_title,
            "Course Name": course_name,
            "Teacher Name": teacher_name,
            "Reason": reason or "No reason provided",
            "ASSESSMENT_LINK": assessment_link,
        }
        
        html_content = self._render_template("14_result_rejected.html", replacements)
        
        if not html_content:
            logger.error("Failed to render result rejected email template")
            return False
        
        subject = f"Result Request Declined: {quiz_title}"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_quiz_deadline_reminder(
        self,
        to_email: str,
        student_name: str,
        quiz_title: str,
        course_name: str,
        due_date: str,
        time_remaining: str,
        max_points: Optional[int] = None,
        quiz_link: Optional[str] = None
    ) -> bool:
        """Send reminder email to student when quiz deadline is approaching."""
        quiz_link = quiz_link or f"{self.frontend_url}/student/assessments"
        
        replacements = {
            "Quiz Title": quiz_title,
            "Course Name": course_name,
            "Due Date": due_date,
            "Time Remaining": time_remaining,
            "Max Points": str(max_points) if max_points else "Not specified",
            "QUIZ_LINK": quiz_link,
        }
        
        html_content = self._render_template("15_quiz_deadline_reminder.html", replacements)
        
        if not html_content:
            logger.error("Failed to render quiz deadline reminder email template")
            return False
        
        subject = f"⏰ Reminder: {quiz_title} due soon"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_quiz_published_notification(
        self,
        to_email: str,
        student_name: str,
        quiz_title: str,
        course_name: str,
        teacher_name: str,
        due_date: Optional[str] = None,
        max_points: Optional[int] = None,
        quiz_link: Optional[str] = None
    ) -> bool:
        """Send notification email to student when a new quiz is published."""
        quiz_link = quiz_link or f"{self.frontend_url}/student/assessments"
        
        replacements = {
            "Teacher Name": teacher_name,
            "Course Name": course_name,
            "Quiz Title": quiz_title,
            "Due Date": due_date or "Not specified",
            "Max Points": str(max_points) if max_points else "Not specified",
            "QUIZ_LINK": quiz_link,
        }
        
        html_content = self._render_template("16_quiz_published.html", replacements)
        
        if not html_content:
            logger.error("Failed to render quiz published email template")
            return False
        
        subject = f"New Quiz Available: {quiz_title}"
        return self._send_email(to_email, subject, html_content, student_name)
    
    def send_student_enrolled_notification(
        self,
        to_email: str,
        teacher_name: str,
        student_name: str,
        student_id: str,
        course_name: str,
        enrollment_date: str,
        course_link: Optional[str] = None
    ) -> bool:
        """Send notification email to teacher when a student enrolls in their course."""
        course_link = course_link or f"{self.frontend_url}/teacher/courses"
        
        replacements = {
            "Course Name": course_name,
            "Student Name": student_name,
            "Student ID": student_id,
            "Enrollment Date": enrollment_date,
            "COURSE_LINK": course_link,
        }
        
        html_content = self._render_template("17_student_enrolled.html", replacements)
        
        if not html_content:
            logger.error("Failed to render student enrolled email template")
            return False
        
        subject = f"New Student Enrolled: {course_name}"
        return self._send_email(to_email, subject, html_content, teacher_name)
    
    def send_notification_email(
        self,
        to_email: str,
        to_name: str,
        notification_title: str,
        notification_description: Optional[str] = None,
        action_url: Optional[str] = None
    ) -> bool:
        """
        Send a generic notification email.
        
        Args:
            to_email: Recipient email address
            to_name: Recipient name
            notification_title: Notification title
            notification_description: Notification description (optional)
            action_url: Action URL (optional)
            
        Returns:
            True if email sent successfully
        """
        # Create a simple notification email using welcome template as base
        action_link = action_url or f"{self.frontend_url}/dashboard"
        
        # Simple HTML template for generic notifications
        html_content = f"""
<div style="font-family: -apple-system, BlinkMacOSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f8f9fa;">
  <div style="background-color: white; padding: 32px 28px; border-radius: 8px; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
    {self._load_template("01_email_header.html")}
    <h2 style="color: #334155; font-size: 20px; margin: 0 0 20px 0;">{notification_title}</h2>
    {f'<p style="color: #475569; line-height: 1.6; font-size: 15px; margin: 0 0 24px 0;">{notification_description}</p>' if notification_description else ''}
    <div style="text-align: center; margin: 32px 0;">
      <a href="{action_link}" style="display: inline-block; background-color: #3b82f6; color: white; padding: 14px 32px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 16px;">View Details</a>
    </div>
    {self._load_template("02_email_footer.html")}
  </div>
</div>
"""
        
        subject = notification_title
        return self._send_email(to_email, subject, html_content, to_name)


# Global email service instance
email_service = EmailService()
