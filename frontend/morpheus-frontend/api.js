const CONFIG = {
  API_BASE: 'http://localhost:8000/api/v1',
  WS_BASE: 'ws://localhost:8000/ws'
};

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
  const url = `${CONFIG.API_BASE}${path}`;
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
    headers
  };

  if (body !== null) {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url, options);

  if (response.status === 401) {
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

async function faceVerify(user_id, face_embedding) {
  return apiCall('POST', '/auth/face-verify', { user_id, face_embedding });
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
  return apiCall('POST', '/exams/', examData);
}

async function sendFrame(session_id, frame_base64) {
  return apiCall('POST', '/proctoring/frame', { session_id, frame_base64 });
}

async function sendAudio(session_id, voice_energy, keywords_detected = []) {
  return apiCall('POST', '/proctoring/audio', { session_id, voice_energy, keywords_detected });
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

function connectProctoringWS(session_id, onMessage) {
  const token = getToken();
  const ws = new WebSocket(`${CONFIG.WS_BASE}/proctoring/${session_id}?token=${token}`);
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
  sendRaf,
  sendViolation,
  getIntegrity,
  getResult,
  getExamResults,
  connectProctoringWS,
  getToken,
  setToken,
  clearToken,
  getUser,
  setUser,
  requireAuth
};
