import httpx

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

# Tier-1: direct answer-seeking phrases (high confidence)
TIER1_KEYWORDS = [
    "what is the answer", "tell me the answer", "correct option", "which option is correct",
    "bata do", "batao", "jawab kya", "jawab batao", "sahi jawab", "option kaunsa",
    "answer kya hai", "kya answer", "correct answer", "right answer",
]

# Tier-2: question-reading heuristic keywords
QUESTION_WORDS = [
    "what", "which", "how", "why", "when", "where", "who",
    "kya", "kaun", "kaise", "kyun", "kab", "kahan", "kitna", "kitni",
]


def _check_keywords(transcript: str) -> tuple[int, list[str]]:
    """
    Returns (tier, matched_keywords).
    tier=1 → confirmed cheating phrase
    tier=2 → possible question reading
    tier=0 → no match
    """
    lower = transcript.lower()
    words = lower.split()

    # Tier 1
    matched = [kw for kw in TIER1_KEYWORDS if kw in lower]
    if matched:
        return 1, matched

    # Tier 2: >6 words and contains a question word
    if len(words) > 6 and any(qw in words for qw in QUESTION_WORDS):
        found_qw = [qw for qw in QUESTION_WORDS if qw in words]
        return 2, found_qw

    return 0, []


async def transcribe_audio(audio_bytes: bytes, mime_type: str, api_key: str) -> dict:
    """
    Send audio to Sarvam saaras STT API.
    Returns { transcript, language_code, confidence } or raises on error.
    """
    # Sarvam expects multipart/form-data with the audio file
    files = {"file": ("audio.wav", audio_bytes, mime_type)}
    data = {"model": "saaras:v3", "mode": "transcribe"}
    headers = {"api-subscription-key": api_key}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(SARVAM_STT_URL, headers=headers, files=files, data=data)
        resp.raise_for_status()
        body = resp.json()

    transcript = body.get("transcript", "").strip()
    language_code = body.get("language_code", "unknown")

    return {"transcript": transcript, "language_code": language_code}


async def analyse_speech(audio_bytes: bytes, mime_type: str, api_key: str) -> dict:
    """
    Full pipeline: transcribe → keyword check → return structured result.
    Returns:
      {
        transcript, language_code,
        tier,          # 0=clean 1=confirmed 2=suspicious
        keywords,      # matched keyword list
        violation,     # bool
        confidence,    # float if violation else None
      }
    """
    result = await transcribe_audio(audio_bytes, mime_type, api_key)
    transcript = result["transcript"]

    if not transcript:
        return {**result, "tier": 0, "keywords": [], "violation": False, "confidence": None}

    tier, keywords = _check_keywords(transcript)
    confidence = 0.90 if tier == 1 else (0.65 if tier == 2 else None)

    return {
        **result,
        "tier": tier,
        "keywords": keywords,
        "violation": tier > 0,
        "confidence": confidence,
    }
