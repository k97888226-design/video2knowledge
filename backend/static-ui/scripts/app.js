const API_BASE = '/api/v1';
const SUBTITLE_SUFFIXES = ['.srt', '.ass', '.ssa', '.vtt', '.json'];
const TIMED_MEDIA_SUFFIXES = ['.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.mp3', '.wav', '.m4a', '.flac', '.aac', '.ogg'];
const STEP_ORDER = ['upload', 'parse', 'generate', 'done'];

let activeTaskId = null;
let pollInterval = null;
let lastMarkdown = '';

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initProcessForm();
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
            document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');

            if (btn.dataset.tab === 'results') {
                loadTasks();
            }
        });
    });
}

function initProcessForm() {
    const form = document.getElementById('process-form');
    const subtitleInput = document.getElementById('subtitle-file');
    const mediaInput = document.getElementById('media-file');
    const processBtn = document.getElementById('process-btn');

    [subtitleInput, mediaInput].forEach(input => {
        input.addEventListener('change', () => {
            updateFileName(input);
            updateSubmitState();
            hideError();
        });
    });

    updateSubmitState();

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        hideError();

        const subtitleFile = subtitleInput.files[0];
        const mediaFile = mediaInput.files[0];
        const validation = validateUpload(subtitleFile, mediaFile);

        if (!validation.ok) {
            showError(validation.message);
            return;
        }

        const exportFormats = getSelectedExportFormats();
        if (exportFormats.length === 0) {
            showError('请至少选择一种导出格式。');
            return;
        }

        processBtn.disabled = true;
        processBtn.textContent = '正在生成...';
        activeTaskId = null;
        lastMarkdown = '';
        document.getElementById('process-result').classList.add('hidden');
        showProgress();
        setStep('upload');
        setWorkflowHint('正在上传文件。');

        try {
            const formData = new FormData();
            formData.append('file', mediaFile || subtitleFile);
            if (mediaFile && subtitleFile) {
                formData.append('subtitle_file', subtitleFile);
            }
            formData.append('language', document.getElementById('language').value);
            formData.append('asr_model_size', 'tiny');
            formData.append('enable_word_timestamps', 'false');
            formData.append('export_formats', exportFormats.join(','));

            const response = await fetch(`${API_BASE}/upload/process`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(await readApiError(response));
            }

            const data = await response.json();
            activeTaskId = data.task_id;
            setStep('parse');
            setWorkflowHint('文件已接收，正在等待解析结果。');
            startPolling(data.task_id, () => {
                processBtn.disabled = false;
                processBtn.textContent = '生成学习包';
            }, () => {
                processBtn.disabled = false;
                processBtn.textContent = '生成学习包';
            });
        } catch (error) {
            showError(toFriendlyError(error.message));
            markStepError();
            processBtn.disabled = false;
            processBtn.textContent = '生成学习包';
        }
    });

    function updateSubmitState() {
        const subtitleFile = subtitleInput.files[0];
        const mediaFile = mediaInput.files[0];
        const validation = validateUpload(subtitleFile, mediaFile);
        processBtn.disabled = !validation.ok;
        setWorkflowHint(validation.ok ? '可以开始生成学习包。' : '选择字幕文件后即可开始。');
    }
}

function initResultsTab() {
    document.getElementById('refresh-tasks').addEventListener('click', loadTasks);
    document.getElementById('clear-tasks').addEventListener('click', () => {
        document.getElementById('task-list').innerHTML = '<p class="empty-state">当前列表已清空显示。</p>';
    });
}

function updateFileName(input) {
    const target = document.getElementById(`${input.id}-name`);
    if (!target) return;
    target.textContent = input.files[0] ? input.files[0].name : '未选择文件';
}

function validateUpload(subtitleFile, mediaFile) {
    if (!subtitleFile && !mediaFile) {
        return { ok: false, message: '请先上传字幕文件，或上传视频并同时选择字幕文件。' };
    }

    if (subtitleFile && !SUBTITLE_SUFFIXES.includes(getFileSuffix(subtitleFile.name))) {
        return { ok: false, message: '字幕文件格式不支持，请使用 .srt、.vtt、.ass 或 .json。' };
    }

    if (mediaFile && !TIMED_MEDIA_SUFFIXES.includes(getFileSuffix(mediaFile.name))) {
        return { ok: false, message: '视频或音频格式不支持，请更换常见的 mp4、mov、mp3、wav 等文件。' };
    }

    if (mediaFile && !subtitleFile) {
        return { ok: false, message: '当前稳定模式需要字幕文件，请同时选择对应字幕。' };
    }

    return { ok: true };
}

function getSelectedExportFormats() {
    return Array.from(document.querySelectorAll('input[name="export-format"]:checked'))
        .map(checkbox => checkbox.value);
}

async function loadTasks() {
    const list = document.getElementById('task-list');
    list.innerHTML = '<p class="empty-state">正在加载...</p>';

    try {
        const response = await fetch(`${API_BASE}/tasks?limit=50`);
        if (!response.ok) {
            throw new Error(await readApiError(response));
        }

        const tasks = await response.json();
        if (tasks.length === 0) {
            list.innerHTML = '<p class="empty-state">暂无处理结果。</p>';
            return;
        }

        list.innerHTML = tasks.map(task => renderTaskItem(task)).join('');
        list.querySelectorAll('[data-view-task]').forEach(button => {
            button.addEventListener('click', () => viewTaskResult(button.dataset.viewTask));
        });
    } catch (error) {
        list.innerHTML = `<p class="empty-state error-text">${escapeHtml(toFriendlyError(error.message))}</p>`;
    }
}

function renderTaskItem(task) {
    const statusClass = `status-${task.status}`;
    const statusText = getStatusText(task.status);
    const error = task.error ? `<small class="error-text">${escapeHtml(toFriendlyError(task.error))}</small>` : '';
    const viewButton = task.status === 'completed'
        ? `<button class="btn btn-secondary" type="button" data-view-task="${escapeHtml(task.task_id)}">查看结果</button>`
        : '';

    return `
      <div class="task-item">
        <div class="task-info">
          <strong>${escapeHtml(task.task_id.substring(0, 8))}</strong>
          <span class="task-status-badge ${statusClass}">${statusText}</span>
          <small>${Math.round(task.progress || 0)}% · ${escapeHtml(task.message || '')}</small>
          ${error}
        </div>
        ${viewButton}
      </div>`;
}

function startPolling(taskId, onComplete, onFailure) {
    if (pollInterval) clearInterval(pollInterval);

    const poll = async () => {
        try {
            const response = await fetch(`${API_BASE}/task/${taskId}`);
            if (!response.ok) {
                throw new Error(await readApiError(response));
            }

            const task = await response.json();
            updateProgress(task);

            if (task.status === 'completed') {
                clearInterval(pollInterval);
                setStep('done');
                setWorkflowHint('学习包已生成。');
                displayResult(task.result);
                if (onComplete && activeTaskId === taskId) onComplete(task.result);
            } else if (task.status === 'failed') {
                clearInterval(pollInterval);
                markStepError();
                showError(toFriendlyError(task.error || '处理失败，请检查文件后重试。'));
                if (onFailure && activeTaskId === taskId) onFailure(task.error);
            }
        } catch (error) {
            clearInterval(pollInterval);
            markStepError();
            showError(toFriendlyError(error.message));
            if (onFailure) onFailure(error);
        }
    };

    poll();
    pollInterval = setInterval(poll, 1500);
}

function showProgress() {
    document.getElementById('process-progress').classList.remove('hidden');
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-text').textContent = '0%';
    document.getElementById('progress-status').textContent = '准备上传文件';
    resetSteps();
}

function updateProgress(task) {
    const progress = Math.round(task.progress || 0);
    document.getElementById('progress-bar').style.width = `${progress}%`;
    document.getElementById('progress-text').textContent = `${progress}%`;
    document.getElementById('progress-status').textContent = getProgressMessage(task);

    if (task.status === 'completed') {
        setStep('done');
    } else if (task.status === 'summarizing' || progress >= 70) {
        setStep('generate');
    } else if (task.status === 'processing' || task.status === 'transcribing' || progress >= 20) {
        setStep('parse');
    } else {
        setStep('upload');
    }
}

function resetSteps() {
    STEP_ORDER.forEach(step => {
        const item = document.getElementById(`step-${step}`);
        item.classList.remove('active', 'done', 'error');
    });
}

function setStep(activeStep) {
    const activeIndex = STEP_ORDER.indexOf(activeStep);
    STEP_ORDER.forEach((step, index) => {
        const item = document.getElementById(`step-${step}`);
        item.classList.toggle('done', index < activeIndex || activeStep === 'done');
        item.classList.toggle('active', index === activeIndex && activeStep !== 'done');
        item.classList.remove('error');
    });
}

function markStepError() {
    const active = document.querySelector('.step-item.active') || document.getElementById('step-upload');
    active.classList.add('error');
    document.getElementById('progress-status').textContent = '处理失败，请查看提示。';
}

function setWorkflowHint(message) {
    document.getElementById('workflow-hint').textContent = message;
}

function displayResult(result) {
    if (!result) return;

    const container = document.getElementById('process-result');
    const resultContent = document.getElementById('result-content');
    const title = result.title || result.file_name || '学习包';
    lastMarkdown = result.exports?.markdown || '';

    document.getElementById('result-title').textContent = title;
    document.getElementById('result-meta').textContent = buildResultMeta(result);

    resultContent.innerHTML = `
      <div class="result-layout">
        <div class="result-main">
          ${renderSummary(result)}
          ${renderKnowledgeTree(result.knowledge_tree)}
        </div>
        <aside class="result-side">
          ${renderStatistics(result.statistics)}
          ${renderKeywords(result.keywords)}
        </aside>
      </div>
      ${renderInterviewQuestions(result.interview_questions)}
      ${renderFlashcards(result.flashcards)}
      ${renderMarkdownExport(result.exports)}
    `;

    bindResultActions();
    container.classList.remove('hidden');
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function buildResultMeta(result) {
    const parts = [];
    if (result.source_type) parts.push(getSourceTypeText(result.source_type));
    if (result.file_name) parts.push(result.file_name);
    if (result.statistics?.total_sentences) parts.push(`${result.statistics.total_sentences} 句`);
    return parts.join(' · ');
}

function renderSummary(result) {
    return `
      <section class="result-panel">
        <div class="result-panel-header">
          <span class="result-label">摘要</span>
          <h3>核心内容</h3>
        </div>
        <p>${escapeHtml(result.summary || '暂无摘要。')}</p>
      </section>`;
}

function renderKnowledgeTree(tree) {
    return `
      <section class="result-panel result-panel-primary">
        <div class="result-panel-header">
          <span class="result-label">时间戳知识树</span>
          <h3>按时间组织的知识结构</h3>
        </div>
        <div class="knowledge-tree">
          ${tree ? renderTree(tree, true) : '<p class="empty-state">暂无知识树。</p>'}
        </div>
      </section>`;
}

function renderStatistics(statistics) {
    if (!statistics) return '';

    return `
      <section class="side-panel">
        <h3>统计</h3>
        <div class="statistics">
          <div class="stat-card">
            <div class="stat-value">${statistics.total_sentences || 0}</div>
            <div class="stat-label">句子</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">${statistics.total_words || 0}</div>
            <div class="stat-label">词汇</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">${statistics.chars_no_spaces || 0}</div>
            <div class="stat-label">字符</div>
          </div>
        </div>
      </section>`;
}

function renderKeywords(keywords) {
    if (!keywords || keywords.length === 0) return '';

    return `
      <section class="side-panel">
        <h3>关键词</h3>
        <div class="keyword-list">
          ${keywords.map(keyword => `<span class="keyword-tag">${escapeHtml(keyword)}</span>`).join('')}
        </div>
      </section>`;
}

function renderInterviewQuestions(items) {
    if (!items || items.length === 0) return '';

    return `
      <section class="result-panel">
        <div class="result-panel-header">
          <span class="result-label">面试问答</span>
          <h3>可直接复述的问答</h3>
        </div>
        <div class="qa-list">
          ${items.map((item, index) => `
            <article class="qa-item">
              <div class="qa-question">Q${index + 1}. ${escapeHtml(item.question || '')}</div>
              ${renderTimestamp(item.timestamp)}
              <div class="qa-answer">${escapeHtml(item.answer || '')}</div>
              ${item.evidence ? `<div class="evidence">原文依据：${escapeHtml(item.evidence)}</div>` : ''}
            </article>
          `).join('')}
        </div>
      </section>`;
}

function renderFlashcards(cards) {
    if (!cards || cards.length === 0) return '';

    return `
      <section class="result-panel">
        <div class="result-panel-header">
          <span class="result-label">复习卡片</span>
          <h3>问题与答案</h3>
        </div>
        <div class="flashcard-grid">
          ${cards.map(card => `
            <article class="flashcard">
              <div class="flashcard-front">${escapeHtml(card.front || '')}</div>
              ${renderTimestamp(card.timestamp)}
              <div class="flashcard-back">${escapeHtml(card.back || '')}</div>
            </article>
          `).join('')}
        </div>
      </section>`;
}

function renderMarkdownExport(exports) {
    const markdown = exports?.markdown || '';
    const exportButtons = exports
        ? Object.entries(exports)
            .filter(([, content]) => content)
            .map(([format]) => `<button class="btn btn-secondary" type="button" data-download-export="${escapeHtml(format)}">下载 ${escapeHtml(format)}</button>`)
            .join('')
        : '';

    return `
      <section class="result-panel export-panel">
        <div class="result-panel-header">
          <span class="result-label">Markdown 导出</span>
          <h3>复习材料</h3>
        </div>
        <div class="export-actions">
          <button class="btn btn-primary" type="button" data-copy-markdown ${markdown ? '' : 'disabled'}>复制 Markdown</button>
          <button class="btn btn-secondary" type="button" data-download-markdown ${markdown ? '' : 'disabled'}>下载 Markdown</button>
          ${exportButtons}
        </div>
        <textarea class="markdown-preview" readonly>${escapeHtml(markdown || '本次结果没有生成 Markdown。')}</textarea>
      </section>`;
}

function renderTree(node, isRoot = false, depth = 0) {
    if (!node || depth > 5) return '';

    const children = node.children && node.children.length > 0
        ? `<div class="tree-children">${node.children.map(child => renderTree(child, false, depth + 1)).join('')}</div>`
        : '';

    return `
      <article class="tree-node ${isRoot ? 'root' : ''}">
        <div class="tree-title">${escapeHtml(node.title || '')}</div>
        ${node.timestamp_start !== undefined ? `<div class="timestamp">${formatTimeRange(node.timestamp_start, node.timestamp_end)}</div>` : ''}
        ${node.content ? `<div class="tree-content">${escapeHtml(truncate(node.content, 220))}</div>` : ''}
        ${node.keywords && node.keywords.length > 0 ? `<div class="keyword-list compact">${node.keywords.map(keyword => `<span class="keyword-tag">${escapeHtml(keyword)}</span>`).join('')}</div>` : ''}
        ${children}
      </article>`;
}

function renderTimestamp(timestamp) {
    if (!timestamp) return '';
    return `<div class="timestamp">${escapeHtml(timestamp.label || '')}</div>`;
}

function bindResultActions() {
    const copyBtn = document.querySelector('[data-copy-markdown]');
    const markdownBtn = document.querySelector('[data-download-markdown]');

    if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
            await copyText(lastMarkdown);
            copyBtn.textContent = '已复制';
            setTimeout(() => { copyBtn.textContent = '复制 Markdown'; }, 1400);
        });
    }

    if (markdownBtn) {
        markdownBtn.addEventListener('click', () => {
            downloadText(lastMarkdown, `video2knowledge-${Date.now()}.md`);
        });
    }

    document.querySelectorAll('[data-download-export]').forEach(button => {
        button.addEventListener('click', () => downloadExport(activeTaskId, button.dataset.downloadExport));
    });
}

async function viewTaskResult(taskId) {
    try {
        const response = await fetch(`${API_BASE}/task/${taskId}`);
        if (!response.ok) {
            throw new Error(await readApiError(response));
        }

        const task = await response.json();
        if (task.result) {
            activeTaskId = taskId;
            displayResult(task.result);
            document.querySelector('[data-tab="process"]').click();
        }
    } catch (error) {
        showError(toFriendlyError(error.message));
    }
}

function downloadExport(taskId, format) {
    if (!taskId || !format) return;
    window.open(`${API_BASE}/task/${taskId}/export/${format}`, '_blank');
}

async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
}

function downloadText(text, filename) {
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

async function readApiError(response) {
    const text = await response.text();
    try {
        const data = JSON.parse(text);
        if (typeof data.detail === 'string') return data.detail;
        if (Array.isArray(data.detail)) return data.detail.map(item => item.msg || item.type).join('；');
        return JSON.stringify(data);
    } catch {
        return text || `HTTP ${response.status}`;
    }
}

function showError(message) {
    const banner = document.getElementById('error-banner');
    banner.textContent = message;
    banner.classList.remove('hidden');
}

function hideError() {
    document.getElementById('error-banner').classList.add('hidden');
}

function toFriendlyError(message) {
    const text = String(message || '');

    if (text.includes('Failed to fetch')) {
        return '无法连接到服务器，请确认服务正在运行。';
    }
    if (text.includes('Unsupported file type')) {
        return '文件格式不支持，请更换字幕文件或常见视频文件。';
    }
    if (text.includes('exceeds') || text.includes('413')) {
        return '文件太大，请换一个更小的文件。';
    }
    if (text.includes('字幕') || text.toLowerCase().includes('subtitle')) {
        return '需要字幕文件，请上传 .srt、.vtt、.ass 或 .json。';
    }
    if (text.includes('not found') || text.includes('不存在')) {
        return '没有找到处理结果，请重新上传文件生成。';
    }

    return text || '处理失败，请稍后重试。';
}

function getProgressMessage(task) {
    if (task.status === 'pending') return '任务已创建，等待处理。';
    if (task.status === 'processing') return task.message || '正在解析字幕内容。';
    if (task.status === 'transcribing') return '正在读取音频内容。';
    if (task.status === 'summarizing') return '正在生成知识树、问答和复习卡片。';
    if (task.status === 'completed') return '学习包已生成。';
    if (task.status === 'failed') return '处理失败，请查看提示。';
    return task.message || '正在处理。';
}

function getStatusText(status) {
    return {
        pending: '等待中',
        processing: '解析中',
        downloading: '下载中',
        transcribing: '转写中',
        summarizing: '生成中',
        completed: '已完成',
        failed: '失败',
    }[status] || status;
}

function getSourceTypeText(sourceType) {
    return {
        subtitle: '字幕',
        video: '视频+字幕',
        audio: '音频+字幕',
    }[sourceType] || sourceType;
}

function getFileSuffix(filename) {
    const index = filename.lastIndexOf('.');
    return index >= 0 ? filename.slice(index).toLowerCase() : '';
}

function formatTimeRange(start, end) {
    return `${formatSeconds(start || 0)} - ${formatSeconds(end || start || 0)}`;
}

function formatSeconds(value) {
    const total = Math.max(0, Math.floor(Number(value) || 0));
    const h = String(Math.floor(total / 3600)).padStart(2, '0');
    const m = String(Math.floor((total % 3600) / 60)).padStart(2, '0');
    const s = String(total % 60).padStart(2, '0');
    return h === '00' ? `${m}:${s}` : `${h}:${m}:${s}`;
}

function truncate(value, maxLength) {
    const text = String(value || '');
    return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}
