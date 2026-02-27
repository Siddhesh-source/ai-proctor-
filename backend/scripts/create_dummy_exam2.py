import asyncio, os

with open(os.path.join(os.path.dirname(__file__), '..', '.env')) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime, timedelta, timezone
from app.core.database import AsyncSessionLocal
from app.models.db import Exam, Question, User
from sqlalchemy import select


async def create():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == 'demo.professor@morpheus.local'))
        prof = res.scalar_one()
        now = datetime.now(timezone.utc)
        exam = Exam(
            professor_id=prof.id,
            title='Python Fundamentals Quiz',
            type='mixed',
            duration_minutes=45,
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(hours=24),
            negative_marking=0.0,
            randomize_questions=False,
        )
        db.add(exam)
        await db.flush()

        questions = [
            Question(
                exam_id=exam.id,
                text="What is the output of: print(type([]))?",
                type='mcq',
                options={
                    'A': "<class 'list'>",
                    'B': "<class 'array'>",
                    'C': "<class 'tuple'>",
                    'D': "<class 'dict'>",
                },
                correct_answer='A',
                marks=4.0,
                order_index=1,
            ),
            Question(
                exam_id=exam.id,
                text='Which keyword is used to define a generator function in Python?',
                type='mcq',
                options={'A': 'return', 'B': 'async', 'C': 'yield', 'D': 'generate'},
                correct_answer='C',
                marks=4.0,
                order_index=2,
            ),
            Question(
                exam_id=exam.id,
                text='What is the time complexity of looking up a key in a Python dictionary?',
                type='mcq',
                options={'A': 'O(n)', 'B': 'O(log n)', 'C': 'O(n^2)', 'D': 'O(1)'},
                correct_answer='D',
                marks=4.0,
                order_index=3,
            ),
            Question(
                exam_id=exam.id,
                text='Explain Python decorators and give a real-world use case.',
                type='subjective',
                correct_answer=(
                    'A decorator is a function that wraps another function to extend its behavior '
                    'without modifying it. They use the @ syntax. Real-world use cases include '
                    'authentication checks, logging, caching, and rate limiting.'
                ),
                keywords=['decorator', 'function', 'wrap', 'behavior', 'logging', 'authentication', 'caching'],
                marks=10.0,
                order_index=4,
            ),
            Question(
                exam_id=exam.id,
                text='Write a program that reads N integers (one per line, first line is N) and prints them in reverse order.',
                type='code',
                correct_answer='',
                marks=12.0,
                order_index=5,
                code_language='python',
                test_cases=[
                    {'input': '3\n1\n2\n3',            'expected_output': '3\n2\n1'},
                    {'input': '5\n10\n20\n30\n40\n50', 'expected_output': '50\n40\n30\n20\n10'},
                    {'input': '1\n42',                 'expected_output': '42'},
                ],
            ),
            Question(
                exam_id=exam.id,
                text='Write a program that reads an integer n and prints all prime numbers up to n (one per line).',
                type='code',
                correct_answer='',
                marks=16.0,
                order_index=6,
                code_language='python',
                test_cases=[
                    {'input': '10', 'expected_output': '2\n3\n5\n7'},
                    {'input': '20', 'expected_output': '2\n3\n5\n7\n11\n13\n17\n19'},
                    {'input': '2',  'expected_output': '2'},
                    {'input': '1',  'expected_output': ''},
                ],
            ),
        ]
        db.add_all(questions)
        await db.commit()
        print('Created exam:', str(exam.id))
        print('Title:', exam.title)
        print('Total marks:', sum(q.marks for q in questions))
        for q in questions:
            print(f'  [{q.type:10}] ({q.marks}pts) {q.text[:65]}')


asyncio.run(create())
