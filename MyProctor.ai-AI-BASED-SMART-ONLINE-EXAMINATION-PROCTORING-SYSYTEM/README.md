# Run Scripts

## Local (FastAPI)
```bash
python -m pip install -r app/requirements.txt
python scripts/migrate.py
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker
```bash
docker build -t morpheus-backend .
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db" \
  -e SECRET_KEY="change-me" \
  morpheus-backend
```

## Serverless (AWS Lambda)
```bash
serverless deploy
```

# Current Features
- Authentication: register/login with JWT; face embedding registration/verification.
- Exams: create exams with questions, start sessions, fetch questions (randomized if enabled), submit answers, finish & background grading.
- Results: per-session results and exam-level summaries.
- Proctoring (API-based): frame analysis (YOLO), audio/RAF signals, generic violations, integrity scoring.
- WebSocket proctoring channel: real-time violation reporting and integrity feedback.
- Grading: MCQ exact-match + negative marking; subjective NLP scoring; optional code grading via Judge0.

## PROPOSED SYSTEM
# A) Authentication with Image Verification
1) Basic Login, Register, Forgot Password, Change Password, etc
2) System allows only one login per user, so that user can’t do any unfair means.
3) System will verify image of user at every time of login and also in exam using face recognition technology.


# B) Professor 
1) Using AI , professor can generate questions & answers, the 2 types of questions & answer can be generated: objective & subjective.
2) Professor can create exam, view exam history, share details of exam with students, view questions, update, delete questions, but update & delete questions will not work at the time of exam & after the exam.
3) Professor can insert marks of subjective & practical exam & also publish the results, view results.
4) Professor can view Live Monitoring of Exam & also can view proctoring logs of the students.
5) Professor can report problems, recharge exam wallet, view FAQ, contact us.

# C) Students
1) Give/Take Exam
2) Check Exam History
3) Check Results
4) Report Problems

# D) Exam 
1) Types of Exam Supported:
    - Objective
    - Subjective
    - Practical 
2) If webpage is refresh then the timer will not be refreshed
3) Support for Negative Marking.
4) Support for randomize questions.
5) Support for Calculator for Mathematical type of Exam
6) Support for 20 types of Compilers/Interpreter for  programming practical type of Exam.
7) For Objective type of Exam:
     - Single page per question
     - Bookmark question 
      - Question Grid with previous & next button
      - At the time of exam submission all questions statistics will be showed to user for confirmation. 


# E) Proctoring 
1) Making logs of window events whenever user changes tab or opens a new tab.
2) Making logs of audio frequency at every 5 seconds of the students.
3) Detection of Mobile phone.
4) Detection of  More than 1 person in the exam.
5) Gaze Estimation: Estimating the position of student body & eyes movements.
6) Taking Students images logs at every 5 seconds.
7) CUT, COPY, PASTE, Taking Screenshots Function is disabled.
8) VM detection & Detection of Screen-Sharing applications. [Support Desktop App Only]


