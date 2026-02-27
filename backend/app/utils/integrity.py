WEIGHTS = {
    "phone_detected": 0.30,
    "gaze_away": 0.25,
    "raf_tab_switch": 0.20,
    "tab_switch": 0.20,
    "speech_detected": 0.15,
    "multiple_faces": 0.10,
    "no_mouse": 0.10,
    "window_resize": 0.15,
    "copy_paste": 0.10,
    "multiple_monitors": 0.15,
    "screen_share_detected": 0.40,
    "screenshot_attempt": 0.10,
    "speech_cheating": 0.35,
}


def update_integrity(current_score: float, violation_type: str, confidence: float) -> float:
    penalty = WEIGHTS.get(violation_type, 0.05) * confidence * 100
    return round(max(0.0, current_score - penalty), 2)
