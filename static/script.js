const form = document.getElementById('prompt-form');
const promptInput = document.getElementById('prompt');
const results = document.getElementById('results');
const button = document.getElementById('submit-btn');

// TODO: replace with your AI agent endpoint
const API_URL = '/api/travel';

let currentThreadId = localStorage.getItem("travel_thread_id") || null;

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
 
// Minimal markdown: **bold**, "* " bullets, blank-line paragraphs
function formatText(text) {
  const lines = escapeHtml(text).split('\n');
  let html = '';
  let inList = false;
 
  for (const raw of lines) {
    const line = raw.trim().replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    if (line.startsWith('* ')) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += '<li>' + line.slice(2) + '</li>';
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      if (line) html += '<p>' + line + '</p>';
    }
  }
  if (inList) html += '</ul>';
  return html;
}
 
function renderResponse(data) {
  // The API currently returns the text in "amswer" (typo), so check all names
  const text = data.answer || data.amswer || data.itinerary || '';
  let html = '';
 
  if (text) {
    html += formatText(text);
  }
 
  if (Array.isArray(data.hotel_results) && data.hotel_results.length) {
    html += '<h2>Hotel sources</h2><ul>';
    for (const h of data.hotel_results) {
      if (h.url && /^https?:\/\//i.test(h.url)) {
        html += '<li><a href="' + escapeHtml(h.url) +
          '" target="_blank" rel="noopener noreferrer">' +
          escapeHtml(h.title || h.url) + '</a></li>';
      }
    }
    html += '</ul>';
  }
 
  if (data.flight_results) {
    html += '<details><summary>Flight search details</summary><pre>' +
      escapeHtml(data.flight_results) + '</pre></details>';
  }
 
  return html || '<p>No result returned.</p>';
}
 
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const prompt = promptInput.value.trim();
  if (!prompt) return;
 
  button.disabled = true;
  results.textContent = 'Planning your trip...';
 
  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: prompt,
        thread_id: currentThreadId
      })
    });
 
    if (!response.ok) throw new Error('Request failed');
 
    const data = await response.json();
    if (data.thread_id) currentThreadId = data.thread_id;
    results.innerHTML = renderResponse(data);
  } catch (err) {
    results.textContent = 'Something went wrong. Please try again.';
  } finally {
    button.disabled = false;
  }
});
 
