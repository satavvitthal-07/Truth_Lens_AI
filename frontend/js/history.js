import { apiRequest, formatDate } from './api.js';
import './app.js';

const tbody = document.querySelector('#history-rows');
const errorBox = document.querySelector('#history-error');

function textCell(row, value) {
  const cell = document.createElement('td');
  cell.textContent = value ?? '—';
  row.append(cell);
  return cell;
}

function showError(message) {
  errorBox.textContent = message;
  errorBox.classList.add('visible');
}

async function loadHistory() {
  errorBox.classList.remove('visible');
  tbody.replaceChildren();
  const loading = document.createElement('tr');
  const loadingCell = document.createElement('td');
  loadingCell.colSpan = 7;
  loadingCell.textContent = 'Loading history…';
  loading.append(loadingCell);
  tbody.append(loading);
  try {
    const { analyses } = await apiRequest('/history');
    tbody.replaceChildren();
    if (!analyses.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 7;
      cell.className = 'empty-state';
      cell.textContent = 'No analyses are saved yet.';
      row.append(cell);
      tbody.append(row);
      return;
    }
    for (const item of analyses) {
      const row = document.createElement('tr');
      const file = textCell(row, item.display_name);
      const report = document.createElement('a');
      report.href = `result.html?id=${encodeURIComponent(item.analysis_id)}`;
      report.textContent = item.display_name || 'Open report and preview';
      const mediaStatus = document.createElement('span');
      mediaStatus.className = 'small';
      mediaStatus.textContent = item.media_url
        ? (item.media_available ? 'Preview available' : 'Saved media missing')
        : 'No media retained';
      file.replaceChildren(report, mediaStatus);
      textCell(row, item.media_type);
      textCell(row, item.prediction);
      textCell(row, typeof item.score === 'number' ? item.score.toFixed(4) : '—');
      textCell(row, item.model_id || 'Unavailable');
      textCell(row, formatDate(item.created_at));
      const actions = document.createElement('td');
      const removeButton = document.createElement('button');
      removeButton.type = 'button';
      removeButton.className = 'button button-quiet';
      removeButton.textContent = 'Delete';
      removeButton.setAttribute('aria-label', `Delete analysis and saved media for ${item.display_name}`);
      removeButton.addEventListener('click', async () => {
        if (!window.confirm(`Delete the analysis and its retained media for "${item.display_name}"?`)) return;
        removeButton.disabled = true;
        try {
          await apiRequest(`/history/${encodeURIComponent(item.analysis_id)}`, { method: 'DELETE' });
          await loadHistory();
        } catch (error) {
          removeButton.disabled = false;
          showError(error.message);
        }
      });
      actions.append(removeButton);
      row.append(actions);
      tbody.append(row);
    }
  } catch (error) {
    tbody.replaceChildren();
    showError(error.message);
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 7;
    cell.className = 'empty-state';
    cell.textContent = 'History could not be loaded.';
    row.append(cell);
    tbody.append(row);
  }
}

document.querySelector('#refresh-history').addEventListener('click', loadHistory);
document.querySelectorAll('[data-year]').forEach((element) => { element.textContent = String(new Date().getFullYear()); });
loadHistory();
