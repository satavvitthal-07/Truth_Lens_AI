import { API_BASE, apiRequest, formatBytes, formatDate } from './api.js';
import './app.js';

const content = document.querySelector('#report-content');
const errorBox = document.querySelector('#report-error');
const reportTitle = document.querySelector('#report-title');
const reportSubtitle = document.querySelector('#report-subtitle');

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function metric(label, value) {
  const wrapper = element('div');
  wrapper.append(element('span', 'metric-label', label), element('strong', '', value ?? '—'));
  return wrapper;
}

function renderReport(analysis) {
  reportTitle.textContent = analysis.display_name || 'Analysis report';
  reportSubtitle.textContent = `${analysis.media_type || 'Media'} screening · ${formatDate(analysis.created_at)}`;
  content.replaceChildren();

  const top = element('div', 'grid grid-2');
  const resultCard = element('section', 'card card-body');
  const resultHead = element('div', 'report-score');
  const hasScore = typeof analysis.score === 'number';
  const formattedScore = hasScore ? analysis.score.toFixed(4) : 'N/A';
  const score = element('div', 'score-ring', formattedScore);
  score.setAttribute('aria-label', hasScore ? `Model score ${formattedScore}` : 'No model score available');
  const resultText = element('div');
  const statusLabels = {
    completed: 'Screening signal',
    unavailable: 'Model unavailable',
    failed: 'Processing failed',
  };
  resultText.append(element('span', 'pill amber', statusLabels[analysis.status] || 'Inconclusive'));
  resultText.append(element('h2', '', analysis.prediction || 'Inconclusive'));
  resultText.append(element('p', '', hasScore
    ? 'Score shown is the model output for this analysis; it is not represented as a calibrated probability.'
    : analysis.error_message || 'No inference score is available for this record.'));
  resultHead.append(score, resultText);
  resultCard.append(resultHead);
  const limitation = element('div', 'result-banner');
  limitation.append(element('strong', '', 'Interpret cautiously'));
  limitation.append(element('p', '', analysis.media_type === 'video'
    ? 'This is a summary of independently screened video frames. No temporal, audio or lip-sync analysis was performed.'
    : 'A model indicator cannot prove whether an image is authentic or AI-generated.'));
  resultCard.append(limitation);
  top.append(resultCard);

  const details = element('section', 'card card-body');
  details.append(element('h3', '', 'Analysis details'));
  const meta = element('div', 'report-meta');
  meta.append(
    metric('File', analysis.display_name),
    metric('Media type', analysis.media_type),
    metric('File size', formatBytes(analysis.file_size)),
    metric('Model', analysis.model_id || 'Not configured'),
    metric('Model revision', analysis.model_revision || 'Not specified'),
    metric('Top model label', analysis.top_label || '—'),
    metric('Processing time', typeof analysis.processing_ms === 'number' ? `${analysis.processing_ms} ms` : '—'),
    metric('Created', formatDate(analysis.created_at)),
  );
  details.append(meta);
  top.append(details);
  content.append(top);

  const mediaCard = element('section', 'card card-body');
  mediaCard.style.marginTop = '20px';
  mediaCard.append(element('h3', '', 'Saved media'));
  if (!analysis.media_url) {
    mediaCard.append(element('p', 'small', 'No media was retained for this analysis.'));
  } else if (!analysis.media_available) {
    mediaCard.append(element('p', 'small', 'The saved media file is missing or unavailable.'));
  } else {
    const mediaUrl = `${API_BASE}${analysis.media_url}`;
    const mediaError = element('p', 'small');
    mediaError.hidden = true;
    mediaError.setAttribute('role', 'status');
    if (analysis.media_type === 'image') {
      const image = element('img', 'media-preview');
      image.src = mediaUrl;
      image.alt = `Saved uploaded image: ${analysis.display_name || 'image'}`;
      image.loading = 'lazy';
      image.addEventListener('error', () => {
        mediaError.textContent = 'The saved image could not be loaded. It may have been removed from storage.';
        mediaError.hidden = false;
      });
      mediaCard.append(image, mediaError);
    } else if (analysis.media_type === 'video') {
      const video = element('video', 'media-preview');
      video.src = mediaUrl;
      video.controls = true;
      video.preload = 'metadata';
      video.setAttribute('aria-label', `Saved uploaded video: ${analysis.display_name || 'video'}`);
      video.addEventListener('error', () => {
        mediaError.textContent = 'The saved video could not be played. It may have been removed from storage.';
        mediaError.hidden = false;
      });
      mediaCard.append(video, mediaError);
    } else {
      mediaCard.append(element('p', 'small', 'This media type cannot be previewed.'));
    }
  }
  content.append(mediaCard);

  if (analysis.media_type === 'video' && Array.isArray(analysis.frames)) {
    const frameCard = element('section', 'card card-body');
    frameCard.style.marginTop = '20px';
    frameCard.append(element('h3', '', 'Sampled frame summary'));
    const list = element('div', 'table-wrap');
    const table = element('table');
    const head = element('thead');
    const heading = element('tr');
    for (const label of ['Frame', 'Timestamp', 'Prediction', 'Model label', 'Model score']) heading.append(element('th', '', label));
    head.append(heading);
    const body = element('tbody');
    for (const frame of analysis.frames) {
      const row = element('tr');
      row.append(element('td', '', String(frame.index)), element('td', '', `${frame.timestamp_seconds.toFixed(2)} s`), element('td', '', frame.prediction), element('td', '', frame.top_label || '—'), element('td', '', typeof frame.score === 'number' ? frame.score.toFixed(4) : '—'));
      body.append(row);
    }
    table.append(head, body);
    list.append(table);
    frameCard.append(list);
    content.append(frameCard);
  }

  if (Array.isArray(analysis.scores) && analysis.scores.length) {
    const scoreCard = element('section', 'card card-body');
    scoreCard.style.marginTop = '20px';
    scoreCard.append(element('h3', '', 'Relevant model outputs'));
    const scoreList = element('div', 'table-wrap');
    const scoreTable = element('table');
    const scoreHeader = element('thead');
    const scoreHeading = element('tr');
    scoreHeading.append(element('th', '', 'Model label'), element('th', '', 'Raw score'));
    scoreHeader.append(scoreHeading);
    const scoreBody = element('tbody');
    for (const item of analysis.scores) {
      const row = element('tr');
      row.append(element('td', '', item.label), element('td', '', Number(item.score).toFixed(4)));
      scoreBody.append(row);
    }
    scoreTable.append(scoreHeader, scoreBody);
    scoreList.append(scoreTable);
    scoreCard.append(scoreList);
    content.append(scoreCard);
  }

  const actions = element('div');
  actions.style.cssText = 'display:flex;gap:12px;flex-wrap:wrap;margin-top:24px';
  const retry = element('a', 'button button-primary', 'Analyze another file');
  retry.href = analysis.media_type === 'video' ? 'video.html' : 'upload.html';
  const history = element('a', 'button button-secondary', 'View history');
  history.href = 'history.html';
  actions.append(retry, history);
  content.append(actions);
}

async function loadReport() {
  const id = new URLSearchParams(window.location.search).get('id');
  if (!id) {
    errorBox.textContent = 'No analysis ID was provided. Choose a record from analysis history.';
    errorBox.classList.add('visible');
    reportTitle.textContent = 'Report not found';
    return;
  }
  try {
    renderReport(await apiRequest(`/history/${encodeURIComponent(id)}`));
  } catch (error) {
    errorBox.textContent = error.message;
    errorBox.classList.add('visible');
    reportTitle.textContent = 'Report unavailable';
    reportSubtitle.textContent = 'The saved analysis could not be retrieved.';
  }
}

document.querySelectorAll('[data-year]').forEach((node) => { node.textContent = String(new Date().getFullYear()); });
loadReport();
