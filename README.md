# EduGuard AI — AI-Powered Student Early Warning & Academic Risk Detection System

> **Part 1 Foundation** — Full academic monitoring platform with multi-role dashboards, assessment engine, question bank, attendance, assignments, and faculty feedback. AI integration (IBM watsonx.ai Granite) scheduled for Phase 2.

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

## Phase 2 Roadmap (AI Integration)

- [ ] IBM watsonx.ai Granite integration
- [ ] Academic Health Score calculation
- [ ] Risk level prediction (Low / Medium / High)
- [ ] AI-powered personalized recommendations
- [ ] AI Chatbot for students
- [ ] Automatic email alerts for at-risk students

---

## License

MIT License — Educational & Academic use.
