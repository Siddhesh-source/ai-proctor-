# Quatarly - AI-Powered Online Examination Platform

**Version:** 2.1.0  
**Status:** Production Ready  
**Last Updated:** February 27, 2026

---

## Overview

Quatarly is a comprehensive AI-powered online examination platform with intelligent proctoring, automated grading, and advanced analytics. The system uses machine learning models for real-time monitoring, NLP-based subjective answer evaluation, and provides detailed performance reports.

---

## Key Features

### 1. Authentication & Security
- JWT-based authentication with token expiry
- Role-based access control (Student/Professor)
- Face embedding registration and verification
- Password hashing with bcrypt
- Single session per user enforcement

### 2. Exam Management
- Create and manage exams with multiple question types
- Support for MCQ, Subjective, and Code questions
- Question randomization
- Negative marking support
- Exam scheduling with start/end times
- Real-time session monitoring

### 3. AI-Powered Proctoring
- **Object Detection (YOLOv10n):** Detects multiple persons, phones, books
- **Tab Switching Detection:** RequestAnimationFrame monitoring
- **Audio Analysis:** Speech/noise detection
- **Violation Logging:** Comprehensive tracking with severity levels
- **Integrity Scoring:** Real-time calculation based on violations
- **WebSocket Monitoring:** Live proctoring feed for professors

### 4. Automated Grading
- **MCQ:** Instant exact-match grading with negative marking
- **Subjective:** NLP-based semantic similarity scoring (85-90% accuracy)
- **Background Processing:** Automatic grading on exam completion
- **Multi-component Scoring:** Semantic (60%), Keywords (25%), Structure (15%)

### 5. Advanced Analytics
- **Comparative Analysis:** Class averages, percentiles, rankings
- **Time Tracking:** Per-question time spent analysis
- **Performance Categories:** Excellent/Above Average/Average/Below Average
- **Question Analytics:** Difficulty index, success rates
- **Time Efficiency:** Fast/Average/Slow classification

### 6. Professional Reports
- **PDF Generation:** Student and professor reports with charts
- **Email Delivery:** Automatic report distribution via SMTP
- **Comprehensive Metrics:** Scores, violations, time analytics
- **Visual Analytics:** Bar charts, pie charts, timelines
- **Downloadable:** Direct PDF download via API

---

## Technology Stack

### Backend
- **Framework:** FastAPI (Python 3.10+)
- **Database:** PostgreSQL with asyncpg
- **ORM:** SQLAlchemy (async)
- **Authentication:** JWT (python-jose)
- **Password Hashing:** bcrypt

### AI/ML Models
- **Object Detection:** YOLOv10n (Ultralytics)
- **NLP:** SentenceTransformer (all-MiniLM-L6-v2)
- **Performance:** 50-60ms per frame, 10-20ms per text

### Additional Libraries
- **PDF Generation:** ReportLab
- **Charts:** Matplotlib
- **Email:** aiosmtplib
- **WebSocket:** FastAPI WebSocket
- **Validation:** Pydantic

---

## Quick Start

### Prerequisites
- Python 3.10 or higher
- PostgreSQL database
- SMTP server (for email features)

### Installation

1. **Clone the repository:**
```bash
cd MyProctor.ai-AI-BASED-SMART-ONLINE-EXAMINATION-PROCTORING-SYSYTEM
```

2. **Install dependencies:**
```bash
pip install -r app/requirements.txt
```

3. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. **Setup database:**
```bash
python scripts/migrate.py create
```

5. **Run the server:**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

6. **Access the application:**
- API: http://localhost:8000
- Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/

---

## Configuration

### Environment Variables

Create a `.env` file with the following:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/quatarly

# Security
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# SMTP (Email)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@quatarly.com
SMTP_FROM_NAME=Quatarly

# Application
PROJECT_NAME=Quatarly
VERSION=2.1.0
```

### Gmail SMTP Setup
1. Enable 2-Factor Authentication
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use app password in `SMTP_PASSWORD`

---

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login and get JWT token
- `GET /api/v1/auth/me` - Get current user info

### Exams (Professor)
- `POST /api/v1/exams` - Create exam
- `GET /api/v1/exams` - List all exams
- `GET /api/v1/exams/{exam_id}` - Get exam details
- `PUT /api/v1/exams/{exam_id}` - Update exam
- `DELETE /api/v1/exams/{exam_id}` - Delete exam

### Exams (Student)
- `GET /api/v1/exams/available` - List available exams
- `POST /api/v1/exams/{exam_id}/start` - Start exam session
- `GET /api/v1/exams/{exam_id}/questions` - Get questions
- `POST /api/v1/exams/{exam_id}/submit-answer` - Submit answer
- `POST /api/v1/exams/{exam_id}/finish` - Finish exam

### Proctoring
- `POST /api/v1/proctoring/frame` - Process video frame
- `POST /api/v1/proctoring/audio` - Process audio
- `POST /api/v1/proctoring/raf` - Tab switch detection
- `POST /api/v1/proctoring/violation` - Log violation
- `GET /api/v1/proctoring/{session_id}/integrity` - Get integrity score
- `WS /ws/proctoring/{session_id}` - WebSocket monitoring

### Results
- `GET /api/v1/results/{session_id}` - Get session results
- `GET /api/v1/results/{session_id}/pdf` - Download PDF report
- `POST /api/v1/results/{session_id}/email` - Email report
- `GET /api/v1/results/{session_id}/analytics` - Get analytics
- `GET /api/v1/results/exam/{exam_id}` - Get exam summary
- `GET /api/v1/results/exam/{exam_id}/pdf` - Professor report

---

## Usage Examples

### 1. Register and Login

```python
import requests

# Register
response = requests.post("http://localhost:8000/api/v1/auth/register", json={
    "email": "student@example.com",
    "password": "SecurePass123",
    "full_name": "John Doe",
    "role": "student"
})

# Login
response = requests.post("http://localhost:8000/api/v1/auth/login", data={
    "username": "student@example.com",
    "password": "SecurePass123"
})
token = response.json()["access_token"]
```

### 2. Create Exam (Professor)

```python
headers = {"Authorization": f"Bearer {token}"}

exam = requests.post("http://localhost:8000/api/v1/exams", 
    headers=headers,
    json={
        "title": "Python Programming Exam",
        "description": "Mid-term exam",
        "duration_minutes": 60,
        "total_marks": 100,
        "passing_marks": 40,
        "randomize_questions": True,
        "negative_marking": True,
        "questions": [
            {
                "question_text": "What is Python?",
                "question_type": "mcq",
                "marks": 5,
                "correct_answer": "A programming language",
                "options": ["A snake", "A programming language", "A framework"]
            }
        ]
    }
).json()
```

### 3. Take Exam (Student)

```python
# Start exam
session = requests.post(
    f"http://localhost:8000/api/v1/exams/{exam_id}/start",
    headers=headers
).json()

# Get questions
questions = requests.get(
    f"http://localhost:8000/api/v1/exams/{exam_id}/questions",
    params={"session_id": session["id"]},
    headers=headers
).json()

# Submit answer
requests.post(
    f"http://localhost:8000/api/v1/exams/{exam_id}/submit-answer",
    headers=headers,
    json={
        "session_id": session["id"],
        "question_id": questions[0]["id"],
        "answer": "A programming language"
    }
)

# Finish exam
requests.post(
    f"http://localhost:8000/api/v1/exams/{exam_id}/finish",
    headers=headers,
    json={"session_id": session["id"]}
)
```

### 4. Get Results with Analytics

```python
# Get comprehensive analytics
analytics = requests.get(
    f"http://localhost:8000/api/v1/results/{session_id}/analytics",
    headers=headers
).json()

print(f"Score: {analytics['total_score']}")
print(f"Rank: {analytics['comparative_analytics']['rank']}")
print(f"Percentile: {analytics['comparative_analytics']['percentile']}%")
print(f"Performance: {analytics['comparative_analytics']['performance_category']}")
```

### 5. Send Report via Email

```python
# Email PDF report to student
response = requests.post(
    f"http://localhost:8000/api/v1/results/{session_id}/email",
    headers=headers
)
print(response.json())  # {"message": "Email sent successfully"}
```

---

## Deployment

### Docker

```bash
# Build image
docker build -t quatarly-backend .

# Run container
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db" \
  -e SECRET_KEY="your-secret-key" \
  -e SMTP_USER="your-email@gmail.com" \
  -e SMTP_PASSWORD="your-app-password" \
  quatarly-backend
```

### AWS Lambda (Serverless)

```bash
# Install Serverless Framework
npm install -g serverless

# Deploy
serverless deploy

# View logs
serverless logs -f api
```

### Production Checklist
- [ ] Set strong SECRET_KEY (min 32 characters)
- [ ] Configure production database
- [ ] Set up SMTP credentials
- [ ] Enable HTTPS/SSL
- [ ] Configure CORS properly
- [ ] Set up monitoring and logging
- [ ] Configure backup strategy
- [ ] Test all endpoints
- [ ] Load test the system
- [ ] Set up CI/CD pipeline

---

## Testing

### Run All Tests

```bash
# Test ML models
python test_models.py

# Test API endpoints
python test_all_endpoints.py

# Test new features
python test_new_features.py

# Check database
python check_db.py
```

### Test Coverage
- ✅ ML models (YOLO + SentenceTransformer)
- ✅ Authentication and authorization
- ✅ Exam CRUD operations
- ✅ Proctoring detection
- ✅ Grading algorithms
- ✅ PDF generation
- ✅ Email delivery
- ✅ Analytics calculations

---

## Performance

### Response Times
- Health check: <10ms
- Authentication: 50-100ms
- Exam operations: 100-200ms
- Frame processing: 50-60ms (YOLO)
- Grading: 10-20ms per answer (NLP)

### Model Performance
- **YOLOv10n:** 50-60ms per frame (~16-20 FPS)
- **SentenceTransformer:** 10-20ms per sentence
- **Load Time:** 2-5 seconds at startup
- **Memory:** ~220MB total for both models

---

## Architecture

### Database Schema
- **users** - User accounts and authentication
- **exams** - Exam definitions and configuration
- **questions** - Exam questions with answers
- **sessions** - Active exam sessions
- **responses** - Student answers with time tracking
- **proctoring_logs** - Violation records
- **results** - Final graded results

### Key Design Patterns
- Async/await throughout for non-blocking I/O
- Background tasks for grading
- WebSocket for real-time monitoring
- Singleton pattern for ML model loading
- Repository pattern for database access

---

## Security

### Implemented Measures
- Password hashing with bcrypt
- JWT token authentication
- Token expiry enforcement
- Role-based access control
- Input validation with Pydantic
- SQL injection prevention (SQLAlchemy)
- CORS configuration
- No sensitive data in logs

---

## Troubleshooting

### Common Issues

**Database Connection Error:**
```bash
# Check DATABASE_URL in .env
# Ensure PostgreSQL is running
# Verify credentials
```

**ML Models Not Loading:**
```bash
# Models download automatically on first run
# Ensure internet connection
# Check disk space (~500MB needed)
```

**Email Not Sending:**
```bash
# Verify SMTP credentials
# Use Gmail app password (not regular password)
# Check firewall settings
```

**Proctoring Not Working:**
```bash
# Ensure YOLO model is loaded
# Check frame format (base64 encoded)
# Verify session_id is valid
```

---

## Support & Documentation

- **API Documentation:** http://localhost:8000/docs
- **Project Handover Guide:** See PROJECT_HANDOVER.md
- **Test Guide:** See test_new_features.py

---

## License

Proprietary - All rights reserved

---

## Contributors

Development Team - Quatarly Platform

---

**For detailed handover information, see PROJECT_HANDOVER.md**
