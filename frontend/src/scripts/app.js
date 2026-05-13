const API_BASE = '/api/v1';

let activeTaskId = null;
let pollInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initProcessForm();
    initBatchForm();
    initResultsTab();
});

function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const tabId = 'tab-' + btn.dataset.tab;
            document.getElementById(tabId).classList.add('active');

            if (btn.dataset.tab === 'results') {
                loadTasks();
            }
        });
    });
}

function initProcessForm() {
    const form = document.getElementById('process-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const url = document.getElementById('video-url').value.trim();
        if (!url) return;

        const btn = document.getElementById('process-btn');
        btn.disabled = true;
        btn.textContent = '⏳ 处理中...';

        const progress = document.getElementById('process-progress');
        progress.classList.remove('hidden');
        document.getElementById('process-result').classList.add('hidden');

        const exportFormats = [];
        document.querySelectorAll('input[name="export-format"]:checked').forEach(cb => {
            exportFormats.push(cb.value);
        });

        const payload = {
            url: url,
            language: document.getElementById('language').value,
            asr_model_size: document.getElementById('asr-model').value,
            summarization_method: document.getElementById('summary-method').value,
            use_asr: document.getElementById('use-asr').checked,
            generate_mindmap: document.getElementById('generate-mindmap').checked,
            export_formats: exportFormats,
        };

        try {
            const resp = await fetch(`${API_BASE}/video/process`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            const data = await resp.json();
            activeTaskId = data.task_id;
            startPolling(data.task_id, (result) => {
                displayResult(result);
                btn.disabled = false;
                btn.textContent = '🚀 开始处理';
            });

        } catch (err) {
            showError('请求失败: ' + err.message);
            btn.disabled = false;
            btn.textContent = '🚀 开始处理';
        }
    });
}

function initBatchForm() {
    const form = document.getElementById('batch-form');
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const urlsText = document.getElementById('batch-urls').value.trim();
        const urls = urlsText.split('\n').filter(u => u.trim());

        if (urls.length === 0) return;

        const payload = {
            urls: urls,
            language: document.getElementById('batch-language').value,
            asr_model_size: document.getElementById('batch-model').value,
            export_formats: ['markdown', 'json'],
        };

        try {
            const resp = await fetch(`${API_BASE}/batch/process`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            const data = await resp.json();
            const progress = document.getElementById('batch-progress');
            progress.classList.remove('hidden');

            const list = document.getElementById('batch-task-list');
            list.innerHTML = `<p>已创建 ${data.total} 个任务，批次ID: ${data.batch_id}</p>`;

            data.task_ids.forEach((taskId, i) => {
                list.innerHTML += `
                  <div class="task-item" id="batch-task-${taskId}">
                    <div class="task-info">
                      <strong>任务 ${i + 1}</strong>
                      <span class="task-status-badge status-pending">等待中</span>
                    </div>
                  </div>`;
            });

            data.task_ids.forEach(taskId => {
                startPolling(taskId, null, (taskId, status) => {
                    const el = document.getElementById(`batch-task-${taskId}`);
                    if (el) {
                        const badge = el.querySelector('.task-status-badge');
                        badge.textContent = status.message;
                        badge.className = `task-status-badge status-${status.status}`;
                    }
                });
            });

        } catch (err) {
            showError('批量处理失败: ' + err.message);
        }
    });
}

function initResultsTab() {
    document.getElementById('refresh-tasks').addEventListener('click', loadTasks);
    document.getElementById('clear-tasks').addEventListener('click', async () => {
        const list = document.getElementById('task-list');
        list.innerHTML = '<p>已清除显示（任务仍在后台）</p>';
    });
}

async function loadTasks() {
    const list = document.getElementById('task-list');
    try {
        const resp = await fetch(`${API_BASE}/tasks?limit=50`);
        const tasks = await resp.json();

        if (tasks.length === 0) {
            list.innerHTML = '<p>暂无处理任务</p>';
            return;
        }

        list.innerHTML = tasks.map(t => {
            const statusClass = `status-${t.status}`;
            const statusText = {
                pending: '等待中', processing: '处理中',
                downloading: '下载中', transcribing: '转录中',
                summarizing: '摘要生成中', completed: '已完成', failed: '失败'
            }[t.status] || t.status;

            return `
              <div class="task-item">
                <div class="task-info">
                  <strong>${t.task_id.substring(0, 8)}...</strong>
                  <span class="task-status-badge ${statusClass}">${statusText}</span>
                  ${t.progress > 0 ? ` - ${t.progress}%` : ''}
                  <br><small>${t.message}</small>
                  ${t.error ? `<br><small style="color:var(--danger)">${t.error}</small>` : ''}
                </div>
                ${t.status === 'completed' ? `
                  <button class="btn btn-secondary" onclick="viewTaskResult('${t.task_id}')">
                    查看
                  </button>` : ''}
              </div>`;
        }).join('');

    } catch (err) {
        list.innerHTML = '<p>加载失败</p>';
    }
}

function startPolling(taskId, onComplete, onStatusChange) {
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/task/${taskId}`);
            const task = await resp.json();

            document.getElementById('progress-bar').style.width = task.progress + '%';
            document.getElementById('progress-text').textContent = `${task.progress}%`;
            document.getElementById('progress-status').textContent = task.message;

            if (onStatusChange) {
                onStatusChange(taskId, task);
            }

            if (task.status === 'completed') {
                clearInterval(pollInterval);
                document.getElementById('progress-status').textContent = '✅ 处理完成!';
                if (onComplete && activeTaskId === taskId) {
                    onComplete(task.result);
                }
            } else if (task.status === 'failed') {
                clearInterval(pollInterval);
                document.getElementById('progress-status').textContent = '❌ 处理失败: ' + (task.error || '');
            }
        } catch (err) {
            console.error('轮询错误:', err);
        }
    }, 1500);
}

function displayResult(result) {
    if (!result) return;

    const container = document.getElementById('process-result');
    container.classList.remove('hidden');

    let html = '';

    if (result.statistics) {
        html += `
          <div class="statistics">
            <div class="stat-card">
              <div class="stat-value">${result.statistics.total_sentences || 0}</div>
              <div class="stat-label">句子数</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">${result.statistics.total_words || 0}</div>
              <div class="stat-label">词汇数</div>
            </div>
            <div class="stat-card">
              <div class="stat-value">${result.statistics.chars_no_spaces || 0}</div>
              <div class="stat-label">字符数</div>
            </div>
          </div>`;
    }

    if (result.keywords) {
        html += '<div class="result-section"><h3>🔑 关键词</h3>';
        result.keywords.forEach(kw => {
            html += `<span class="keyword-tag">${kw}</span>`;
        });
        html += '</div>';
    }

    if (result.summary) {
        html += `
          <div class="result-section">
            <h3>📝 摘要</h3>
            <p>${result.summary}</p>
          </div>`;
    }

    if (result.knowledge_tree) {
        html += '<div class="result-section"><h3>🌳 知识框架</h3>';
        html += renderTree(result.knowledge_tree, true);
        html += '</div>';
    }

    if (result.exports) {
        html += '<div class="result-section"><h3>📥 导出</h3><div class="export-buttons">';
        for (const [format, content] of Object.entries(result.exports)) {
            if (content) {
                html += `<button class="btn btn-secondary" onclick="downloadExport('${activeTaskId}', '${format}')">⬇ ${format}</button>`;
            }
        }
        html += '</div></div>';
    }

    document.getElementById('result-content').innerHTML = html;
    container.scrollIntoView({ behavior: 'smooth' });
}

function renderTree(node, isRoot = false, depth = 0) {
    if (!node) return '';

    let html = `<div class="tree-node ${isRoot ? 'root' : ''}">`;
    html += `<div class="tree-title">${node.title || ''}</div>`;
    if (node.content) {
        html += `<div class="tree-content">${node.content.substring(0, 200)}</div>`;
    }
    if (node.keywords && node.keywords.length > 0) {
        html += node.keywords.map(k => `<span class="keyword-tag">${k}</span>`).join(' ');
    }

    if (node.children && node.children.length > 0 && depth < 5) {
        node.children.forEach(child => {
            html += renderTree(child, false, depth + 1);
        });
    }

    html += '</div>';
    return html;
}

async function downloadExport(taskId, format) {
    window.open(`${API_BASE}/task/${taskId}/export/${format}`, '_blank');
}

async function viewTaskResult(taskId) {
    try {
        const resp = await fetch(`${API_BASE}/task/${taskId}`);
        const task = await resp.json();
        if (task.result) {
            activeTaskId = taskId;
            displayResult(task.result);
            document.getElementById('process-result').scrollIntoView({ behavior: 'smooth' });
        }
    } catch (err) {
        showError('加载结果失败');
    }
}

function showError(msg) {
    alert(msg);
}
