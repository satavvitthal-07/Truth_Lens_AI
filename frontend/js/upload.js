import { apiRequest, formatBytes } from './api.js';
import './app.js';

const isVideoPage = window.location.pathname.endsWith('/video.html');
const form = document.querySelector(isVideoPage ? '#video-form' : '#image-form');
const fileInput = document.querySelector(isVideoPage ? '#video-file' : '#image-file');
const chooseButton = document.querySelector('#choose-file');
const clearButton = document.querySelector('#clear-file');
const submitButton = document.querySelector('#analyze-button');
const dropZone = document.querySelector('#drop-zone');
const previewWrap = document.querySelector('#preview-wrap');
const description = document.querySelector('#file-description');
const alertBox = document.querySelector('#upload-error');
const processingNote = document.querySelector('#processing-note');
const preview = document.querySelector(isVideoPage ? '#video-preview' : '#image-preview');
let previewUrl = null;
let submitting = false;

function showError(message) {
  alertBox.textContent = message;
  alertBox.classList.add('visible');
}

function clearError() {
  alertBox.textContent = '';
  alertBox.classList.remove('visible');
}

function isAllowed(file) {
  if (isVideoPage) {
    return file.type === 'video/mp4' && file.name.toLowerCase().endsWith('.mp4') && file.size <= 50 * 1024 * 1024;
  }
  const allowed = new Map([
    ['image/jpeg', ['.jpg', '.jpeg']],
    ['image/png', ['.png']],
  ]);
  const extension = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
  return Boolean(allowed.get(file.type)?.includes(extension)) && file.size <= 10 * 1024 * 1024;
}

function setSelectedFile(file) {
  clearError();
  if (!file) return;
  if (!file.size || !isAllowed(file)) {
    showError(isVideoPage
      ? 'Choose an MP4 video no larger than 50 MB. The backend also enforces duration and video integrity.'
      : 'Choose a JPG, JPEG, or PNG image no larger than 10 MB.');
    fileInput.value = '';
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    preview.removeAttribute('src');
    previewWrap.hidden = true;
    submitButton.disabled = true;
    clearButton.hidden = true;
    return;
  }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  preview.src = previewUrl;
  previewWrap.hidden = false;
  description.textContent = `${file.name} · ${formatBytes(file.size)}`;
  submitButton.disabled = false;
  clearButton.hidden = false;
}

chooseButton.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => setSelectedFile(fileInput.files?.[0]));
clearButton.addEventListener('click', () => {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  preview.removeAttribute('src');
  previewWrap.hidden = true;
  fileInput.value = '';
  description.textContent = '';
  submitButton.disabled = true;
  clearButton.hidden = true;
  if (processingNote) processingNote.textContent = '';
  clearError();
});

for (const eventName of ['dragenter', 'dragover']) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add('dragover');
  });
}
for (const eventName of ['dragleave', 'drop']) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove('dragover');
  });
}
dropZone.addEventListener('drop', (event) => {
  const [file] = event.dataTransfer?.files || [];
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  setSelectedFile(file);
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (submitting || !fileInput.files?.[0]) return;
  submitting = true;
  submitButton.disabled = true;
  submitButton.innerHTML = '<span class="loading"><span class="spinner" aria-hidden="true"></span>Uploading and analyzing…</span>';
  if (processingNote) {
    processingNote.textContent = isVideoPage
      ? 'Sampling a bounded set of frames. Processing time depends on local model and hardware.'
      : 'Running the configured image screening pipeline.';
  }
  clearError();

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 150_000);
  const body = new FormData();
  body.append('file', fileInput.files[0]);
  const route = isVideoPage ? '/detect/video' : '/detect/image';
  try {
    const result = await apiRequest(route, { method: 'POST', body, signal: controller.signal });
    window.location.assign(`result.html?id=${encodeURIComponent(result.analysis_id)}`);
  } catch (error) {
    const analysisId = error.payload?.analysis_id;
    if (analysisId) {
      window.location.assign(`result.html?id=${encodeURIComponent(analysisId)}`);
      return;
    }
    showError(error.name === 'AbortError'
      ? 'The request timed out. The backend applies its own processing limits; check its terminal output before retrying.'
      : error.message);
    submitting = false;
    submitButton.disabled = false;
    submitButton.textContent = isVideoPage ? 'Screen video frames →' : 'Analyze image →';
    if (processingNote) processingNote.textContent = '';
  } finally {
    window.clearTimeout(timeout);
  }
});

window.addEventListener('pagehide', () => {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
});
