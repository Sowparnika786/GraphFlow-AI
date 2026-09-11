const API_BASE = window.location.port === '8000' ? '' : (window.location.origin.includes('8080') ? 'http://localhost:8000' : 'http://localhost:8000');

let selectedFile = null;
let currentJobId = null;
let pollTimer = null;
let isUploaded = false;

document.addEventListener('DOMContentLoaded', () => {
  initHealthCheck();
  initUploadHandlers();
  initChatHandlers();
  initJudgeGuide();
  initQuickSampleHandlers();
});

// 1. Health Checks
async function initHealthCheck() {
  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      updateHealthBadge('health-kafka', data.kafka_connected);
      updateHealthBadge('health-neo4j', data.neo4j_connected);
      updateHealthBadge('health-api', data.status === 'ok');
    } catch (e) {
      updateHealthBadge('health-kafka', false);
      updateHealthBadge('health-neo4j', false);
      updateHealthBadge('health-api', false);
    }
  };
  checkHealth();
  setInterval(checkHealth, 5000);
}

function updateHealthBadge(id, isOk) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `health-badge ${isOk ? 'ok' : 'unhealthy'}`;
}

// 2. Quick Sample Handlers
function initQuickSampleHandlers() {
  const sampleEmployees = `Name,Department,Salary,City
Arun,Sales,25000,Chennai
Priya,Billing,30000,Coimbatore
Kumar,Sales,28000,Madurai
Meena,HR,32000,Chennai
Rahul,Billing,27000,Salem
Sonia,Sales,29000,Chennai
Vikram,HR,35000,Coimbatore
Kavitha,Billing,31000,Madurai
Deepak,Sales,26000,Chennai
Anitha,HR,33000,Salem
Karthik,Billing,32000,Chennai
Divya,Sales,34000,Coimbatore
Ramesh,Sales,27500,Madurai
Lakshmi,Billing,29500,Chennai
Suresh,HR,31500,Salem
Pooja,Billing,28500,Chennai
Ganesh,Sales,31000,Coimbatore
Swetha,HR,36000,Madurai
Vijay,Billing,33500,Salem
Nisha,Sales,30500,Chennai`;

  const sampleCustomers = `customer_id,customer_name,group,order_id,order_amount,city,status
C001,Ravi Kumar,Billing,O1001,12500,Chennai,Completed
C002,Arun Raj,Support,O1002,8200,Bangalore,Open
C003,Kumar S,Billing,O1003,15300,Chennai,Completed
C004,Priya Nair,Sales,O1004,22100,Kochi,Completed
C005,Meena Devi,Support,O1005,6400,Hyderabad,Pending
C006,Vijay L,Engineering,O1006,18700,Chennai,Completed
C007,Suresh P,Billing,O1007,9500,Coimbatore,Completed
C008,Anitha M,HR,O1008,11200,Madurai,Completed`;

  document.getElementById('btn-sample-employees')?.addEventListener('click', () => {
    const blob = new Blob([sampleEmployees], { type: 'text/csv' });
    const file = new File([blob], 'employees.csv', { type: 'text/csv' });
    handleFileSelected(file);
  });

  document.getElementById('btn-sample-customers')?.addEventListener('click', () => {
    const blob = new Blob([sampleCustomers], { type: 'text/csv' });
    const file = new File([blob], 'datara_sample.csv', { type: 'text/csv' });
    handleFileSelected(file);
  });
}

// 3. Upload & File Handlers
function initUploadHandlers() {
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const btnUpload = document.getElementById('btn-upload');
  const btnClear = document.getElementById('btn-clear-file');

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
    }, false);
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length) {
      handleFileSelected(files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) {
      handleFileSelected(e.target.files[0]);
    }
  });

  btnClear.addEventListener('click', () => {
    selectedFile = null;
    isUploaded = false;
    fileInput.value = '';
    document.getElementById('file-details').classList.add('hidden');
    document.getElementById('preview-card').classList.add('hidden');
    document.getElementById('progress-container').classList.add('hidden');
  });

  btnUpload.addEventListener('click', async () => {
    if (!selectedFile) return;
    await uploadCSV(selectedFile);
  });
}

function handleFileSelected(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) {
    alert("Please select a valid .csv file.");
    return;
  }
  selectedFile = file;
  isUploaded = false;
  document.getElementById('file-name').textContent = file.name;
  document.getElementById('file-size').textContent = `${(file.size / 1024).toFixed(1)} KB`;
  document.getElementById('file-details').classList.remove('hidden');
  
  previewCSVFile(file);
  // Auto-upload immediately so graph is instantly populated!
  uploadCSV(file);
}

// 4. Preview & Ingestion
function previewCSVFile(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const lines = text.split('\n').filter(l => l.trim());
    if (lines.length === 0) return;

    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
    const rows = lines.slice(1, 10).map(line => line.split(',').map(cell => cell.trim().replace(/^"|"$/g, '')));

    const thead = document.getElementById('preview-thead');
    const tbody = document.getElementById('preview-tbody');
    thead.innerHTML = '<th>#</th>' + headers.map(h => `<th>${h}</th>`).join('');
    tbody.innerHTML = rows.map((r, i) => `<tr><td>${i+1}</td>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('');

    document.getElementById('stat-rows').textContent = lines.length - 1;
    document.getElementById('stat-cols').textContent = headers.length;
    document.getElementById('stat-missing').textContent = '0';
    document.getElementById('preview-card').classList.remove('hidden');

    updateStepper('step-upload', 'completed');
  };
  reader.readAsText(file);
}

async function uploadCSV(file) {
  const formData = new FormData();
  formData.append('file', file);

  const progressContainer = document.getElementById('progress-container');
  progressContainer.classList.remove('hidden');

  updateStepper('step-kafka', 'active');

  try {
    const res = await fetch(`${API_BASE}/ingest`, {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      alert(`Upload failed: ${err.detail || 'Server error'}`);
      return;
    }

    const data = await res.json();
    currentJobId = data.job_id;
    isUploaded = true;
    document.getElementById('badge-dataset-id').textContent = `Job ID: ${currentJobId}`;
    
    startStatusPolling(currentJobId);
  } catch (e) {
    alert(`Upload error: ${e.message}`);
  }
}

function startStatusPolling(jobId) {
  if (pollTimer) clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/status?job_id=${jobId}`);
      if (!res.ok) return;
      const data = await res.json();

      document.getElementById('count-loaded').textContent = data.rows_loaded;
      document.getElementById('count-failed').textContent = data.rows_failed;
      document.getElementById('count-total').textContent = data.rows_total;
      
      const pct = data.progress_percentage || 0;
      document.getElementById('progress-bar-fill').style.width = `${pct}%`;
      document.getElementById('progress-percentage').textContent = `${pct}%`;
      document.getElementById('progress-status-text').textContent = `Status: ${data.status.toUpperCase()}`;

      if (data.status === 'loading') {
        updateStepper('step-loader', 'active');
      } else if (data.status === 'complete') {
        clearInterval(pollTimer);
        updateStepper('step-loader', 'completed');
        updateStepper('step-neo4j', 'completed');
        updateStepper('step-chat', 'completed');
        document.getElementById('progress-status-text').textContent = 'Loaded into Neo4j graph successfully!';
      } else if (data.status === 'failed') {
        clearInterval(pollTimer);
        document.getElementById('progress-status-text').textContent = 'Ingestion failed.';
      }
    } catch (e) {
      console.warn("Error polling status:", e);
    }
  }, 500);
}

function updateStepper(stepId, state) {
  const el = document.getElementById(stepId);
  if (!el) return;
  el.className = `step-item ${state}`;
}

// 5. Chat Handlers
function initChatHandlers() {
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  
  document.addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (chip) {
      input.value = chip.getAttribute('data-q');
      form.dispatchEvent(new Event('submit'));
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const question = input.value.trim();
    if (!question) return;

    if (selectedFile && !isUploaded) {
      await uploadCSV(selectedFile);
    }

    appendUserMessage(question);
    input.value = '';

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
      });
      const data = await res.json();
      appendBotMessage(data);
    } catch (err) {
      appendBotMessage({
        answer: "Failed to connect to chat API.",
        cypher: null,
        result: [],
        grounded: false
      });
    }
  });
}

function appendUserMessage(text) {
  const history = document.getElementById('chat-history');
  const msgDiv = document.createElement('div');
  msgDiv.className = 'chat-message user-message';
  msgDiv.innerHTML = `
    <div class="msg-avatar">👤</div>
    <div class="msg-body"><p>${escapeHtml(text)}</p></div>
  `;
  history.appendChild(msgDiv);
  history.scrollTop = history.scrollHeight;
}

function appendBotMessage(data) {
  const history = document.getElementById('chat-history');
  const msgDiv = document.createElement('div');
  msgDiv.className = 'chat-message bot-message';
  
  const groundedBadge = data.grounded 
    ? `<span class="badge-success">✓ Grounded in Neo4j</span>`
    : `<span class="badge-danger">✕ Grounded: False (Not in Dataset)</span>`;

  let cypherBlock = '';
  if (data.cypher) {
    cypherBlock = `
      <div class="cypher-box">
        <div class="code-header">Generated Read-Only Cypher</div>
        <code>${escapeHtml(data.cypher)}</code>
      </div>
    `;
  }

  let resultBlock = '';
  if (data.result && data.result.length > 0) {
    resultBlock = `
      <div class="result-box">
        <div class="code-header">Raw Neo4j Evidence Result</div>
        <pre>${escapeHtml(JSON.stringify(data.result, null, 2))}</pre>
      </div>
    `;
  }

  msgDiv.innerHTML = `
    <div class="msg-avatar">⚡</div>
    <div class="msg-body">
      <p>${escapeHtml(data.answer)}</p>
      <div class="meta-badges" style="margin-top:8px;">
        ${groundedBadge}
      </div>
      ${cypherBlock}
      ${resultBlock}
    </div>
  `;
  history.appendChild(msgDiv);
  history.scrollTop = history.scrollHeight;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// 6. Judge Guide Toggle
function initJudgeGuide() {
  const btnGuide = document.getElementById('btn-judge-guide');
  const btnClose = document.getElementById('btn-close-guide');
  const panel = document.getElementById('judge-guide-panel');

  btnGuide?.addEventListener('click', () => panel.classList.toggle('hidden'));
  btnClose?.addEventListener('click', () => panel.classList.add('hidden'));
}
