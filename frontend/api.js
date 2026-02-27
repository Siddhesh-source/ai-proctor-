const CONFIG = {
  API_CANDIDATES: ['http://127.0.0.1:8000', 'http://localhost:8000']
};

let activeApiOrigin = sessionStorage.getItem('morpheus_api_origin') || CONFIG.API_CANDIDATES[0];

async function canReachOrigin(origin) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1200);
  try {
    const response = await fetch(`${origin}/`, { method: 'GET', signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function resolveApiOrigin(forceProbe = false) {
  if (!forceProbe && activeApiOrigin) return activeApiOrigin;

  for (const origin of CONFIG.API_CANDIDATES) {
    if (await canReachOrigin(origin)) {
      activeApiOrigin = origin;
      sessionStorage.setItem('morpheus_api_origin', origin);
      return activeApiOrigin;
    }
  }

  return activeApiOrigin;
}

function getToken() {
  return sessionStorage.getItem('morpheus_token');
}

function setToken(token) {
  sessionStorage.setItem('morpheus_token', token);
}

function clearToken() {
  sessionStorage.removeItem('morpheus_token');
}

function getUser() {
  return JSON.parse(sessionStorage.getItem('morpheus_user') || 'null');
}

function setUser(user) {
  sessionStorage.setItem('morpheus_user', JSON.stringify(user));
}

async function apiCall(method, path, body = null, requiresAuth = true) {
  const origin = await resolveApiOrigin();
  const url = `${origin}/api/v1${path}`;
  const headers = {
    'Content-Type': 'application/json'
  };

  if (requiresAuth) {
    const token = getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const options = {
    method,
    headers,
    cache: 'no-store'
  };

  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  let response;
  for (let attempt = 1; attempt <= 6; attempt += 1) {
    try {
      response = await fetch(url, options);
      break;
    } catch (error) {
      if (attempt === 2 || attempt === 4) {
        await resolveApiOrigin(true);
      }
      await new Promise((resolve) => setTimeout(resolve, 400 * attempt));
    }
  }

  if (!response) {
    throw new Error('Backend not reachable. Start backend on 127.0.0.1:8000 and retry.');
  }

  if (response.status === 401 && !path.includes('/auth/face-verify')) {
    clearToken();
    window.location.href = 'login.html';
    return null;
  }

  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    data = null;
  }

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : 'Request failed';
    throw new Error(detail);
  }

  return data;
}

async function login(email, password) {
  const result = await apiCall('POST', '/auth/login', { email, password }, false);
  if (result && result.access_token) {
    setToken(result.access_token);
    setUser({ id: result.user_id, role: result.role });
  }
  return result;
}

async function register(email, password, full_name, role) {
  return apiCall('POST', '/auth/register', { email, password, full_name, role }, false);
}

async function getMe() {
  return apiCall('GET', '/auth/me');
}

async function faceVerify(user_id, faceData) {
  if (faceData && faceData.samples) {
    return apiCall('POST', '/auth/face-verify', {
      user_id,
      samples: faceData.samples,
      blink_count: faceData.blink_count || 0,
      action_order: faceData.action_order || [],
      capture_duration_ms: faceData.capture_duration_ms || 0
    }, false);
  }
  return apiCall('POST', '/auth/face-verify', { user_id, face_embedding: faceData }, false);
}

async function getAvailableExams() {
  return apiCall('GET', '/exams/available');
}

async function getProfessorExams() {
  return apiCall('GET', '/exams/professor');
}

async function getExamQuestions(exam_id) {
  return apiCall('GET', `/exams/${exam_id}/questions`);
}

async function startExam(exam_id) {
  return apiCall('POST', `/exams/${exam_id}/start`);
}

async function submitAnswer(exam_id, session_id, question_id, answer) {
  return apiCall('POST', `/exams/${exam_id}/submit-answer`, {
    session_id,
    question_id,
    answer
  });
}

async function finishExam(exam_id, session_id) {
  return apiCall('POST', `/exams/${exam_id}/finish`, { session_id });
}

async function createExam(examData) {
  return apiCall('POST', '/exams', examData);
}

async function sendFrame(session_id, frame_base64) {
  return apiCall('POST', '/proctoring/frame', { session_id, frame_base64 });
}

async function sendAudio(session_id, voice_energy, keywords_detected = []) {
  return apiCall('POST', '/proctoring/audio', { session_id, voice_energy, keywords_detected });
}

async function sendAudioStt(session_id, audio_base64, mime_type) {
  return apiCall('POST', '/proctoring/audio/stt', { session_id, audio_base64, mime_type });
}

async function sendRaf(session_id, delta_ms) {
  return apiCall('POST', '/proctoring/raf', { session_id, delta_ms });
}

async function sendViolation(session_id, violation_type, confidence, payload = {}) {
  return apiCall('POST', '/proctoring/violation', {
    session_id,
    violation_type,
    confidence,
    payload
  });
}

async function getIntegrity(session_id) {
  return apiCall('GET', `/proctoring/${session_id}/integrity`);
}

async function getResult(session_id) {
  return apiCall('GET', `/results/${session_id}`);
}

async function getExamResults(exam_id) {
  return apiCall('GET', `/results/exam/${exam_id}`);
}

async function downloadResultPdf(session_id) {
  const origin = await resolveApiOrigin();
  const url = `${origin}/api/v1/results/${session_id}/pdf`;
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, { headers });
  if (!response.ok) throw new Error('Failed to download PDF');
  const blob = await response.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `exam_report_${session_id.slice(0, 8)}.pdf`;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function emailResult(session_id) {
  return apiCall('POST', `/results/${session_id}/email`);
}

async function getExamLogs(exam_id) {
  return apiCall('GET', `/proctoring/exam/${exam_id}/logs`);
}

async function getLiveFrame(session_id) {
  const stamp = Date.now();
  return apiCall('GET', `/proctoring/session/${session_id}/frame?t=${stamp}`);
}

function connectProctoringWS(session_id, onMessage) {
  const token = getToken();
  const wsBase = activeApiOrigin.replace('http://', 'ws://').replace('https://', 'wss://');
  const ws = new WebSocket(`${wsBase}/ws/proctoring/${session_id}?token=${token}`);
  ws.onmessage = (event) => onMessage(JSON.parse(event.data));
  ws.onerror = (e) => console.error('WS error', e);
  return ws;
}

function requireAuth(allowedRole = null) {
  const user = getUser();
  if (!user || !getToken()) {
    window.location.href = 'login.html';
    return false;
  }
  if (allowedRole && user.role !== allowedRole) {
    window.location.href = 'login.html';
    return false;
  }
  return true;
}

window.Morpheus = {
  login,
  register,
  getMe,
  faceVerify,
  getAvailableExams,
  getProfessorExams,
  getExamQuestions,
  startExam,
  submitAnswer,
  finishExam,
  createExam,
  sendFrame,
  sendAudio,
  sendAudioStt,
  sendRaf,
  sendViolation,
  getIntegrity,
  getLiveFrame,
  getResult,
  getExamResults,
  downloadResultPdf,
  emailResult,
  getExamLogs,
  connectProctoringWS,
  getToken,
  setToken,
  clearToken,
  getUser,
  setUser,
  requireAuth
};
