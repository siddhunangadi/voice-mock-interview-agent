import Vapi from 'https://esm.sh/@vapi-ai/web@2.7.1';

const $ = (id) => document.getElementById(id);
let interviewId = localStorage.getItem('interview_id');
let voice;
let finishing = false;
let voiceState = '';
let refreshVersion = 0;
let questionRevealPending = false;

function show(section) {
  for (const id of ['setup', 'interview', 'results']) $(id).hidden = id !== section;
}

function error(message) {
  $('error').textContent = message;
  $('error').hidden = false;
}

async function api(path, options = {}) {
  const response = await fetch(path, {credentials: 'same-origin', ...options});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const cause = Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`);
    cause.status = response.status;
    throw cause;
  }
  return response.json();
}

function fillList(id, values) {
  $(id).replaceChildren(...values.map(value => {
    const li = document.createElement('li');
    li.textContent = value;
    return li;
  }));
}

function render(data) {
  if (data.status === 'completed' && data.evaluation) {
    const result = data.evaluation;
    show('results');
    $('summary').textContent = result.summary;
    $('score').textContent = result.overall_score == null ? 'Not enough evidence to score' : `Overall score: ${result.overall_score}/100`;
    fillList('strengths', result.strengths);
    fillList('improvements', result.improvements);
    fillList('recommendations', result.recommendations);
    $('topics').replaceChildren(...result.topics.map(topic => {
      const article = document.createElement('article');
      article.className = 'topic';
      const title = document.createElement('h3');
      title.textContent = topic.topic + (topic.score == null ? ' · not assessed' : ` · ${topic.score}/4`);
      const body = document.createElement('p');
      body.textContent = `${topic.feedback} Evidence: ${topic.evidence}`;
      article.append(title, body);
      return article;
    }));
    return;
  }
  show('interview');
  $('status').textContent = voiceState || {ready: 'Ready', active: 'Interrupted', ended: 'Finished'}[data.status] || data.status;
  const question = [...data.turns].reverse().find(turn => turn.role === 'assistant');
  if (!voice || questionRevealPending) {
    $('question').textContent = question?.content || '';
    $('progress').textContent = data.state.stage === 'introduction' ? 'Getting to know you' : data.state.stage === 'motivation' ? 'Your interest in the role' : `Discussion · ${data.context.topics[data.state.topic].name}`;
    questionRevealPending = false;
  }
  $('interview-plan').textContent = 'Areas to explore: ' + data.context.topics.map(topic => topic.name).join(' → ');
  $('start-voice').hidden = data.status !== 'ready';
  $('edit-details').hidden = data.status !== 'ready';
  $('end-voice').hidden = data.status === 'ready';
  $('session-note').textContent = data.status === 'active' && !voice
    ? 'The previous voice connection ended. Finish the interview to see feedback.'
    : data.status === 'ended' ? 'Your questions are complete. Finish to see your feedback.'
      : 'Allow microphone access when your browser asks. Speak naturally after the interviewer finishes.';
  $('transcript').replaceChildren(...data.turns.map(turn => {
    const li = document.createElement('li');
    li.textContent = `${turn.role === 'assistant' ? 'Interviewer' : 'You'}: ${turn.content}`;
    return li;
  }));
}

async function refresh() {
  if (!interviewId) return;
  const id = interviewId, version = ++refreshVersion;
  const data = await api(`/api/interviews/${id}`);
  if (id === interviewId && version === refreshVersion) render(data);
}

$('resume-file').addEventListener('change', async () => {
  const file = $('resume-file').files[0];
  if (!file) return;
  const kind = file.name.split('.').pop().toLowerCase();
  $('error').hidden = true;
  if (!['pdf', 'docx'].includes(kind) || !file.size || file.size > 5 * 1024 * 1024) {
    error('Choose a non-empty PDF or DOCX file under 5 MB.');
    $('resume-file').value = '';
    return;
  }
  $('prepare').disabled = true;
  $('resume-file').disabled = true;
  $('resume').readOnly = true;
  $('upload-status').textContent = 'Reading your resume…';
  try {
    const result = await api(`/api/resume-text?kind=${kind}`, {
      method: 'POST', headers: {'Content-Type': 'application/octet-stream'}, body: file
    });
    $('resume').value = result.text;
    $('upload-status').textContent = `${file.name} — text extracted. Review it below before continuing.`;
  } catch (cause) {
    $('upload-status').textContent = 'Upload could not be read. Your previous text is unchanged.';
    error(cause.message);
  } finally {
    $('prepare').disabled = false;
    $('resume-file').disabled = false;
    $('resume').readOnly = false;
    $('resume-file').value = '';
  }
});

$('interview-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('error').hidden = true;
  voiceState = '';
  $('prepare').disabled = true;
  $('prepare').textContent = 'Preparing…';
  try {
    const result = await api('/api/interviews', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({job_description: $('job-description').value, resume: $('resume').value})
    });
    interviewId = result.id;
    localStorage.setItem('interview_id', interviewId);
    await refresh();
  } catch (cause) { error(cause.message); }
  finally { $('prepare').disabled = false; $('prepare').textContent = 'Prepare interview'; }
});

$('start-voice').addEventListener('click', async () => {
  $('start-voice').disabled = true;
  $('error').hidden = true;
  voiceState = 'Checking microphone…';
  $('status').textContent = voiceState;
  try {
    const microphone = await navigator.mediaDevices.getUserMedia({audio: true});
    microphone.getTracks().forEach(track => track.stop());
    voiceState = 'Connecting…';
    $('status').textContent = voiceState;
    voice = new Vapi('browser-session', `${location.origin}/voice`);
    voice.on('call-start', () => { voiceState = 'Waiting for interviewer…'; $('status').textContent = voiceState; $('end-voice').hidden = false; });
    voice.on('speech-start', () => {
      questionRevealPending = true;
      voiceState = 'Interviewer speaking';
      $('status').textContent = voiceState;
      refresh().catch(() => {});
    });
    voice.on('speech-end', () => { voiceState = 'Your turn — speak naturally'; $('status').textContent = voiceState; });
    voice.on('call-end', () => {
      voice = null;
      voiceState = 'Voice session ended';
      if (!finishing) refresh().catch(cause => error(cause.message));
    });
    voice.on('error', () => { voiceState = 'Audio connection problem'; $('status').textContent = voiceState; error('Audio could not connect. Check microphone access and your connection. Your progress is saved.'); });
    const call = await voice.start(interviewId);
    if (!call) throw Error('Voice could not start. Please retry.');
    await refresh();
  } catch (cause) {
    if (voice) voice.stop();
    voice = null;
    voiceState = 'Audio could not start';
    await refresh().catch(() => {});
    error(cause.message);
  } finally { $('start-voice').disabled = false; }
});

async function finish() {
  if (finishing || !interviewId) return;
  finishing = true;
  $('error').hidden = true;
  $('end-voice').disabled = true;
  $('status').textContent = 'Preparing feedback…';
  try {
    if (voice) { const call = voice; voice = null; call.stop(); }
    await api(`/api/interviews/${interviewId}/finish`, {method: 'POST'});
    await refresh();
  } catch (cause) {
    await refresh().catch(() => {});
    error(cause.message);
  } finally { finishing = false; $('end-voice').disabled = false; }
}
$('end-voice').addEventListener('click', finish);
$('edit-details').addEventListener('click', () => { localStorage.removeItem('interview_id'); interviewId = null; voiceState = ''; $('error').hidden = true; show('setup'); });
$('new-interview').addEventListener('click', () => { localStorage.removeItem('interview_id'); interviewId = null; voiceState = ''; $('error').hidden = true; show('setup'); });

if (interviewId) refresh().catch(cause => {
  if ([401, 404].includes(cause.status)) { localStorage.removeItem('interview_id'); interviewId = null; }
  show('setup');
  error(cause.message);
});
setInterval(() => { if (voice && !finishing) refresh().catch(() => {}); }, 3000);
