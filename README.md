<div align="center">

# Quatarly
### AI-Powered Online Examination Platform

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://postgresql.org)
[![YOLOv10](https://img.shields.io/badge/YOLOv10n-ML%20Proctoring-FF6F00?style=for-the-badge&logo=opencv&logoColor=white)](https://ultralytics.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](./LICENSE)
[![Version](https://img.shields.io/badge/Version-2.1.0-blueviolet?style=for-the-badge)](https://github.com/Siddhesh-source/ai-proctor-/releases)
[![Status](https://img.shields.io/badge/Status-Production%20Live-brightgreen?style=for-the-badge)](http://13.205.237.112)

<br/>

**[🌐 Live Demo](http://13.205.237.112) · [📖 API Docs](http://13.205.237.112/docs) · [🐛 Report Bug](https://github.com/Siddhesh-source/ai-proctor-/issues) · [✨ Request Feature](https://github.com/Siddhesh-source/ai-proctor-/issues)**

<br/>

> Quatarly is a full-stack AI-powered examination platform with real-time proctoring, face verification, NLP-based grading, and comprehensive analytics — deployed on AWS.

</div>

---

## Live Deployment

| Service | URL |
|---|---|
| Portal | **http://13.205.237.112** |
| API Docs (Swagger) | **http://13.205.237.112/docs** |
| Student Dashboard | http://13.205.237.112/student.html |
| Faculty Dashboard | http://13.205.237.112/faculty.html |
| Register | http://13.205.237.112/register.html |

> Hosted on AWS EC2 (ap-south-1) · PostgreSQL on AWS RDS · Gunicorn + Nginx

---

## Key Features

### Authentication & Security
- JWT-based authentication with token expiry
- Role-based access control (Student / Professor)
- Face embedding registration and verification
- Password hashing with bcrypt
- Single session per user enforcement

### Exam Management
- Create and manage exams with MCQ, Subjective, and Code questions
- Question randomization and negative marking
- Exam scheduling with start/end times
- Real-time session monitoring

### AI-Powered Proctoring
- **Object Detection (YOLOv10n):** Detects multiple persons, phones, books
- **Tab Switching Detection:** RequestAnimationFrame monitoring
- **Audio Analysis:** Speech/noise detection via STT
- **Violation Logging:** Comprehensive tracking with severity levels
- **Integrity Scoring:** Real-time calculation based on violations
- **WebSocket Monitoring:** Live proctoring feed for professors

### Automated Grading
- **MCQ:** Instant exact-match grading with negative marking
- **Subjective:** NLP semantic similarity scoring (85–90% accuracy)
- **Multi-component Scoring:** Semantic (60%) · Keywords (25%) · Structure (15%)
- **Background Processing:** Auto-grading on exam completion

### Advanced Analytics
- Class averages, percentiles, rankings
- Per-question time spent analysis
- Performance categories: Excellent / Above Average / Average / Below Average
- Question difficulty index and success rates

### Professional Reports
- PDF generation with charts for students and professors
- Automatic email delivery via SMTP
- Direct PDF download via API

---

## Technology Stack

| Layer | Technology |
|---|---|
| **Backend** | FastAPI (Python 3.10+) |
| **Database** | PostgreSQL 17 · SQLAlchemy async · asyncpg |
| **Auth** | JWT (python-jose) · bcrypt |
| **Object Detection** | YOLOv10n (Ultralytics) — 50–60ms/frame |
| **NLP Grading** | SentenceTransformer all-MiniLM-L6-v2 — 10–20ms/answer |
| **Frontend** | Vanilla HTML/CSS/JS |
| **Server** | Gunicorn · UvicornWorker · Nginx |
| **Cloud** | AWS EC2 · AWS RDS · AWS SES |
| **Reports** | ReportLab · Matplotlib |
| **Real-time** | FastAPI WebSocket |

---

## System Architecture

```mermaid
flowchart LR
  subgraph Clients
    Student[Student Browser]
    Faculty[Faculty Browser]
  end

  subgraph Frontend
    UI[Static HTML/CSS/JS\nNginx :80]
  end

  subgraph Backend
    API[FastAPI REST API\nGunicorn :8000]
    WS[WebSocket Proctoring]
    Auth[Auth & RBAC]
    Grading[Grading & Analytics]
    Reports[PDF/Email Service]
  end

  subgraph Data
    DB[(PostgreSQL\nAWS RDS)]
  end

  subgraph ML
    Vision[YOLOv10n Detection]
    NLP[SentenceTransformer Scoring]
  end

  subgraph Integrations
    SMTP[AWS SES SMTP]
  end

  Student --> UI
  Faculty --> UI
  UI --> API
  UI --> WS
  API --> Auth
  API --> DB
  API --> Grading
  Grading --> NLP
  WS --> Vision
  Reports --> SMTP
  API --> Reports
```

## Feature Flow (Student)

```mermaid
sequenceDiagram
  actor Student
  participant UI as Frontend UI
  participant API as Backend API
  participant WS as Proctoring WS
  participant ML as ML Models
  participant DB as PostgreSQL
  participant SMTP as SMTP

  Student->>UI: Login
  UI->>API: Auth (JWT)
  API->>DB: Validate user
  API-->>UI: Token

  Student->>UI: Face verify
  UI->>API: Face verify request
  API->>ML: Compare embeddings
  API-->>UI: Verification result

  Student->>UI: Start exam
  UI->>API: Create session
  API->>DB: Persist session

  loop During exam
    Student->>UI: Camera/Audio/Tab events
    UI->>WS: Stream proctoring signals
    WS->>ML: Detect violations
    WS->>DB: Log events
  end

  Student->>UI: Submit/Finish
  UI->>API: Submit answers
  API->>DB: Store responses
  API->>ML: Grade subjective answers
  API->>DB: Store scores

  Student->>UI: View analytics
  UI->>API: Fetch analytics
  API->>DB: Aggregate results
  API-->>UI: Analytics data

  Student->>UI: Request PDF/Email
  UI->>API: Generate report
  API->>SMTP: Send email
  API-->>UI: Confirmation
```

## Feature Flow (Professor)

```mermaid
sequenceDiagram
  actor Professor
  participant UI as Frontend UI
  participant API as Backend API
  participant WS as Proctoring WS
  participant ML as ML Models
  participant DB as PostgreSQL
  participant SMTP as SMTP

  Professor->>UI: Login
  UI->>API: Auth (JWT)
  API->>DB: Validate user
  API-->>UI: Token

  Professor->>UI: Create/Manage exam
  UI->>API: Create/Update exam
  API->>DB: Persist exam

  Professor->>UI: Monitor live
  UI->>WS: Subscribe to session
  WS->>DB: Stream violations
  WS->>ML: Detect anomalies

  Professor->>UI: View analytics
  UI->>API: Fetch analytics
  API->>DB: Aggregate results
  API-->>UI: Analytics data

  Professor->>UI: Download/Email reports
  UI->>API: Generate report
  API->>SMTP: Send email
  API-->>UI: Confirmation
```

---

## Quick Start

### Prerequisites
- Python 3.10+
- PostgreSQL
- SMTP server (for email)

### Installation

```bash
# 1. Clone
git clone https://github.com/Siddhesh-source/ai-proctor-.git
cd ai-proctor-

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r backend/app/requirements.txt

# 4. Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env with your values

# 5. Run migrations
cd backend
python scripts/migrate.py create

# 6. Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000/docs for the interactive API docs.

---

## Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/quatarly

# Security
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# SMTP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM_EMAIL=noreply@quatarly.com
SMTP_FROM_NAME=Quatarly

# App
PROJECT_NAME=Quatarly
VERSION=2.1.0
```

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login → JWT token |
| GET | `/api/v1/auth/me` | Get current user |

### Exams
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/exams` | Create exam (Professor) |
| GET | `/api/v1/exams/available` | List available exams (Student) |
| POST | `/api/v1/exams/{id}/start` | Start exam session |
| POST | `/api/v1/exams/{id}/submit-answer` | Submit answer |
| POST | `/api/v1/exams/{id}/finish` | Finish exam |

### Proctoring
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/proctoring/frame` | Process video frame (YOLO) |
| POST | `/api/v1/proctoring/audio` | Process audio |
| WS | `/ws/proctoring/{session_id}` | Live monitoring feed |

### Results
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/results/{session_id}` | Get results |
| GET | `/api/v1/results/{session_id}/pdf` | Download PDF |
| POST | `/api/v1/results/{session_id}/email` | Email report |
| GET | `/api/v1/results/{session_id}/analytics` | Full analytics |

Full interactive docs at **http://13.205.237.112/docs**

---

## Performance

| Operation | Response Time |
|---|---|
| Health check | < 10ms |
| Authentication | 50–100ms |
| Exam operations | 100–200ms |
| YOLO frame processing | 50–60ms (~18 FPS) |
| NLP answer grading | 10–20ms |
| PDF generation | 500–1000ms |

---

## Database Schema

```
users            → accounts, roles, face embeddings
exams            → exam config, scheduling
questions        → MCQ / subjective / code questions
sessions         → active exam sessions
responses        → student answers + time tracking
proctoring_logs  → violation records + severity
results          → final graded scores + analytics
```

---

## Deployment

### Production Stack (AWS)
```
EC2 (Ubuntu 24.04)
├── Nginx :80          → reverse proxy + static files
├── Gunicorn :8000     → 3 × UvicornWorker
│   └── FastAPI app
└── systemd            → auto-restart on failure

RDS PostgreSQL 17      → managed database
SES SMTP               → transactional email
```

### Self-host with Gunicorn + Nginx

```bash
# Install
pip install gunicorn uvicorn[standard]

# Run
gunicorn app.main:app \
  --workers 3 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 127.0.0.1:8000
```

### Production Checklist
- [x] Strong `SECRET_KEY` (32+ chars)
- [x] PostgreSQL on managed RDS
- [x] SMTP credentials configured
- [x] Gunicorn + Nginx serving
- [x] systemd auto-restart
- [ ] HTTPS/SSL (Certbot)
- [ ] CI/CD pipeline

---

## Contributing

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for guidelines.

---

## Security

To report a vulnerability see [SECURITY.md](.github/SECURITY.md).

---

## License

[MIT](./LICENSE) © 2026 Team Quatarly
