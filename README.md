# EduGuard AI — AI-Powered Student Early Warning & Academic Risk Detection System

> 
---

## Overview

EduGuard AI is an intelligent academic monitoring platform that helps educational institutions identify students who are academically at risk **before** they fail. The system continuously collects and manages academic data across attendance, assessments, assignments, faculty feedback, and GPA history.

---

## Tech Stack

| Layer        | Technology                                          |
|-------------|-----------------------------------------------------|
| Backend      | Python 3.10+, Flask 3.0, Flask-Login, Flask-WTF    |
| Database     | MySQL 8.0+, SQLAlchemy ORM, Flask-Migrate           |
| Frontend     | Bootstrap 5.3, Bootstrap Icons, Chart.js 4.4        |
| Auth         | Flask-Login, Werkzeug password hashing              |
| Config       | python-dotenv (.env)                                |

---

## Project Structure

```
EduGuard AI/
├── app.py                      # Application factory
├── config.py                   # Environment-based configuration
├── database.py                 # SQLAlchemy + Migrate setup
├── models.py                   # All ORM models
├── forms.py                    # WTForms definitions
├── routes.py                   # Root routes + error handlers
├── requirements.txt
├── .env.example                # Environment template
├── blueprints/
│   ├── auth/routes.py          # Login / Logout / Password
│   ├── admin/routes.py         # Admin CRUD + CSV upload
│   ├── faculty/routes.py       # Attendance, Questions, Assessments
│   └── student/routes.py       # Dashboard, Take Assessment, History
├── templates/
│   ├── base.html               # Master HTML template
│   ├── layout.html             # Sidebar + Topbar layout
│   ├── landing.html            # Public landing page
│   ├── auth/                   # Login, Change Password
│   ├── admin/                  # Admin templates
│   ├── faculty/                # Faculty templates
│   ├── student/                # Student templates
│   └── errors/                 # 404, 403, 500
├── static/
│   ├── css/main.css            # Premium CSS design
│   └── js/main.js              # Sidebar, dark mode, utilities
└── uploads/
    ├── csv/                    # Uploaded CSVs
    └── assignments/
```

---

## Database Schema

| Table                | Description                             |
|---------------------|-----------------------------------------|
| `users`             | Authentication for all roles            |
| `departments`       | Academic departments                    |
| `subjects`          | Subjects linked to departments          |
| `units`             | Units within each subject               |
| `students`          | Student profiles                        |
| `faculty`           | Faculty profiles                        |
| `faculty_subjects`  | Faculty ↔ Subject many-to-many          |
| `attendance`        | Daily per-subject attendance            |
| `assignments`       | Assignment marks per student            |
| `faculty_feedback`  | 4-parameter faculty ratings             |
| `questions`         | Question bank (MCQ, True/False, Fill)   |
| `assessments`       | Scheduled assessments                   |
| `assessment_attempts` | Student attempt sessions              |
| `assessment_answers` | Per-question answers per attempt       |
| `academic_records`  | Semester GPA/CGPA history               |

---

## Quick Start

### 1. Clone & Set Up Environment

```bash
git clone <repo-url>
cd "EduGuard AI"
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your MySQL credentials
```

```env
SECRET_KEY=your-secret-key
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=eduguard_ai
```

### 3. Create Database

```sql
CREATE DATABASE eduguard_ai CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. Run Application

```bash
flask run
# or
python app.py
```

### 5. Create Admin User

```bash
flask seed-admin
```

Default credentials: `admin` / `Admin@123`

### 6. First Steps

1. Login as Admin → Create Departments → Create Subjects → Add Units
2. Add Faculty → Assign Subjects to Faculty
3. Add Students → or Upload via CSV
4. Login as Faculty → Create Question Bank → Schedule Assessments → Mark Attendance
5. Login as Student → Take Assessment → View Dashboard

---

## User Roles

| Role    | Capabilities                                                       |
|---------|--------------------------------------------------------------------|
| Admin   | Full CRUD — Departments, Subjects, Units, Students, Faculty, CSV  |
| Faculty | Attendance, Assignments, Feedback, Question Bank, Assessments      |
| Student | Dashboard, Take Assessments, View History, Academic Records        |

---

## CSV Upload Format

```csv
full_name,student_id,email,username,department_code,semester,batch_year,password
John Doe,STU001,john@example.com,jdoe,CS,3,2022,STU001
```

---

---

# 🚀 Final Project Features

EduGuard AI is now a complete AI-powered Student Early Warning & Academic Risk Detection System with intelligent analytics, automated assessment management, AI-powered recommendations, and IBM watsonx.ai Granite integration.

---

## 🤖 Artificial Intelligence Features

### IBM watsonx.ai Granite Integration

The application integrates IBM watsonx.ai Granite Models to provide intelligent academic assistance and AI-driven insights.

### AI Academic Advisor

- AI-powered academic chatbot
- Personalized study planning
- Subject explanations
- Exam preparation guidance
- Time management assistance
- Learning recommendations

### AI Question Generator

Faculty can generate curriculum-based questions using AI.

Supported Question Types:

- Multiple Choice Questions (MCQ)
- True / False
- Fill in the Blank

Features include:

- Difficulty Selection
- Subject & Unit Selection
- Question Preview
- Edit Before Saving
- Randomized Question Generation
- Duplicate Prevention

### AI Performance Analysis

Automatically generates:

- Overall Performance Analysis
- Concept Understanding
- Confidence Level
- Strong Topics
- Weak Topics
- Personalized Improvement Plan
- Weekly Study Schedule

### Academic Health Monitoring

Academic Health Score is calculated using:

- Attendance
- Assignment Performance
- Assessment Scores
- Faculty Feedback
- Academic History

Students are automatically categorized into:

- 🟢 Low Risk
- 🟡 Medium Risk
- 🔴 High Risk

---

# 📊 Dashboards

## Admin Dashboard

- Institution Analytics
- Department Management
- Faculty Management
- Student Management
- Subject Management
- Unit Management
- Academic Analytics
- Risk Distribution
- Bulk Data Management

## Faculty Dashboard

- Attendance Management
- Assignment Management
- Faculty Feedback
- Question Bank
- AI Question Generator
- Assessment Creation
- Student Performance Reports
- Excel Report Export

## Student Dashboard

- Academic Health Card
- Attendance Summary
- Assignment Performance
- Assessment History
- AI Recommendations
- Performance Timeline
- Academic Analytics

---

# 📂 Bulk Import System

Supports bulk upload of:

- Students
- Faculty
- Departments
- Subjects
- Units

Supported Formats:

- CSV
- Excel (.xlsx)

Features:

- Sample File Download
- Required Column Validation
- Duplicate Detection
- Import Summary
- Error Report

---

# 📤 Faculty Report Export

Faculty can export complete class reports to Excel.

Generated reports include:

- Student Information
- Attendance
- Assignment Scores
- Assessment Scores
- Faculty Rating
- Academic Health Score
- Risk Level
- AI Recommendations

---

# 📧 Automatic Email Alerts

Professional HTML email notifications are automatically sent whenever a student's Academic Health Score reaches Medium or High Risk.

Emails contain:

- Student Details
- Attendance Summary
- Assessment Results
- Faculty Feedback
- Academic Health Score
- Risk Level
- AI Recommendations

---

# 📈 Interactive Analytics

Chart.js powered visualizations include:

- Attendance Trend
- Performance Trend
- Weekly Progress
- Subject-wise Scores
- Academic Health Trend
- Assessment Comparison
- Risk Distribution

---

# 🔒 Security Features

- Role-Based Authentication
- Password Hashing
- CSRF Protection
- Session Management
- Environment Variable Configuration
- Secure IBM watsonx.ai Integration

---

# 🛠 Additional Features

- Responsive Bootstrap 5 Interface
- Dark Mode Support
- Academic Record Management
- Assessment Engine
- Question Bank Management
- Attendance Tracking
- Faculty Feedback System
- Student Performance Tracking
- CSV/Excel Import
- Excel Export
- AI Recommendations
- Automated Risk Detection
- Flash Notifications
- Professional Dashboards

---

# 📦 Project Status

✅ Complete

The EduGuard AI project has been fully developed as a production-ready AI-powered academic monitoring platform integrating traditional academic management with IBM watsonx.ai Granite Models for intelligent educational assistance and early academic risk detection.

---

# 👨‍💻 Developed By

**Kuldeep Vishwakarma**/n
**Princi Patel**/n
**Anuj Gadwal**

**B.Tech Artificial Intelligence**

**SAGE University, Bhopal**

---

⭐ If you found this project helpful, consider giving this repository a Star.

---

## License

MIT License — Educational & Academic use.
