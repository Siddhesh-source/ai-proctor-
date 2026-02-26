"""
Analytics service for comparative analysis and statistics
"""
from typing import Any
import statistics


def calculate_comparative_analytics(
    student_score: float,
    all_scores: list[float],
    student_time: int,
    all_times: list[int]
) -> dict[str, Any]:
    """
    Calculate comparative analytics for a student
    
    Args:
        student_score: Student's total score
        all_scores: List of all students' scores
        student_time: Student's total time in seconds
        all_times: List of all students' times
    
    Returns:
        dict with comparative metrics
    """
    if not all_scores:
        return {}
    
    # Score analytics
    avg_score = statistics.mean(all_scores)
    median_score = statistics.median(all_scores)
    std_dev = statistics.stdev(all_scores) if len(all_scores) > 1 else 0
    
    # Percentile calculation
    sorted_scores = sorted(all_scores)
    rank = sorted_scores.index(student_score) + 1 if student_score in sorted_scores else len(sorted_scores)
    percentile = (rank / len(sorted_scores)) * 100
    
    # Time analytics
    avg_time = statistics.mean(all_times) if all_times else 0
    time_percentile = 0
    if all_times and student_time:
        sorted_times = sorted(all_times)
        time_rank = sorted_times.index(student_time) + 1 if student_time in sorted_times else len(sorted_times)
        time_percentile = (time_rank / len(sorted_times)) * 100
    
    # Performance category
    if student_score >= avg_score + std_dev:
        performance = "Excellent"
    elif student_score >= avg_score:
        performance = "Above Average"
    elif student_score >= avg_score - std_dev:
        performance = "Average"
    else:
        performance = "Below Average"
    
    return {
        "student_score": student_score,
        "class_average": round(avg_score, 2),
        "class_median": round(median_score, 2),
        "standard_deviation": round(std_dev, 2),
        "percentile": round(percentile, 1),
        "rank": rank,
        "total_students": len(all_scores),
        "performance_category": performance,
        "score_difference_from_avg": round(student_score - avg_score, 2),
        "student_time_seconds": student_time,
        "average_time_seconds": round(avg_time, 0) if avg_time else 0,
        "time_percentile": round(time_percentile, 1),
        "time_efficiency": "Fast" if student_time < avg_time else "Slow" if student_time > avg_time else "Average"
    }


def calculate_question_analytics(
    question_responses: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Calculate analytics for a specific question across all students
    
    Args:
        question_responses: List of responses for a question
            Each dict should have: score, marks, time_spent_seconds
    
    Returns:
        dict with question analytics
    """
    if not question_responses:
        return {}
    
    scores = [r.get('score', 0) or 0 for r in question_responses]
    marks = question_responses[0].get('marks', 0) if question_responses else 0
    times = [r.get('time_spent_seconds', 0) or 0 for r in question_responses if r.get('time_spent_seconds')]
    
    # Score analytics
    avg_score = statistics.mean(scores)
    success_rate = (avg_score / marks * 100) if marks > 0 else 0
    
    # Difficulty index (0-1, lower = harder)
    difficulty_index = avg_score / marks if marks > 0 else 0
    
    # Difficulty category
    if difficulty_index >= 0.8:
        difficulty = "Easy"
    elif difficulty_index >= 0.5:
        difficulty = "Medium"
    else:
        difficulty = "Hard"
    
    # Time analytics
    avg_time = statistics.mean(times) if times else 0
    
    return {
        "average_score": round(avg_score, 2),
        "max_marks": marks,
        "success_rate": round(success_rate, 1),
        "difficulty_index": round(difficulty_index, 2),
        "difficulty_category": difficulty,
        "average_time_seconds": round(avg_time, 0),
        "total_attempts": len(question_responses),
        "perfect_scores": sum(1 for s in scores if s >= marks),
        "zero_scores": sum(1 for s in scores if s == 0)
    }


def calculate_exam_analytics(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate overall exam analytics
    
    Args:
        sessions: List of session data
    
    Returns:
        dict with exam-wide analytics
    """
    if not sessions:
        return {}
    
    scores = [s.get('total_score', 0) or 0 for s in sessions]
    integrity_scores = [s.get('integrity_score', 100) or 100 for s in sessions]
    
    # Score distribution
    score_ranges = {
        "90-100": sum(1 for s in scores if s >= 90),
        "80-89": sum(1 for s in scores if 80 <= s < 90),
        "70-79": sum(1 for s in scores if 70 <= s < 80),
        "60-69": sum(1 for s in scores if 60 <= s < 70),
        "Below 60": sum(1 for s in scores if s < 60)
    }
    
    # Integrity distribution
    integrity_ranges = {
        "Excellent (90-100)": sum(1 for i in integrity_scores if i >= 90),
        "Good (75-89)": sum(1 for i in integrity_scores if 75 <= i < 90),
        "Fair (60-74)": sum(1 for i in integrity_scores if 60 <= i < 75),
        "Poor (<60)": sum(1 for i in integrity_scores if i < 60)
    }
    
    return {
        "total_students": len(sessions),
        "average_score": round(statistics.mean(scores), 2),
        "median_score": round(statistics.median(scores), 2),
        "highest_score": max(scores),
        "lowest_score": min(scores),
        "standard_deviation": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0,
        "average_integrity": round(statistics.mean(integrity_scores), 2),
        "score_distribution": score_ranges,
        "integrity_distribution": integrity_ranges,
        "completion_rate": round(
            sum(1 for s in sessions if s.get('status') == 'completed') / len(sessions) * 100, 1
        )
    }


def calculate_time_analytics(responses: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Calculate time-based analytics for responses
    
    Args:
        responses: List of response data with time_spent_seconds
    
    Returns:
        dict with time analytics
    """
    times = [r.get('time_spent_seconds', 0) or 0 for r in responses if r.get('time_spent_seconds')]
    
    if not times:
        return {
            "total_time_seconds": 0,
            "average_time_per_question": 0,
            "fastest_question_time": 0,
            "slowest_question_time": 0
        }
    
    return {
        "total_time_seconds": sum(times),
        "total_time_minutes": round(sum(times) / 60, 1),
        "average_time_per_question": round(statistics.mean(times), 0),
        "fastest_question_time": min(times),
        "slowest_question_time": max(times),
        "time_distribution": {
            "< 1 min": sum(1 for t in times if t < 60),
            "1-3 min": sum(1 for t in times if 60 <= t < 180),
            "3-5 min": sum(1 for t in times if 180 <= t < 300),
            "> 5 min": sum(1 for t in times if t >= 300)
        }
    }
