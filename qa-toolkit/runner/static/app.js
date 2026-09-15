/* ================================================================
   测试执行器前端逻辑
   ================================================================ */

// ================================================================
// 状态管理
// ================================================================

const state = {
    cases: [],
    progress: {},
    cursor: 0,
    submitting: false,
    images: [],
    formMode: false,  // 是否在表单态
    lastSubmit: null,  // 最后一次提交的参数，用于重试
    pipWindow: null    // PiP 窗口引用
};

// ================================================================
// 本地存储
// ================================================================

const STORAGE_KEY = 'qa_runner_progress';

function saveLocalProgress() {
    try {
        const data = {
            cursor: state.cursor,
            records: state.progress.records || {},
            timestamp: Date.now()
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        console.log(`✓ 本地进度已保存: cursor=${state.cursor}, records=${Object.keys(data.records).length}`);
    } catch (e) {
        console.warn('⚠ 本地存储失败:', e);
    }
}

function loadLocalProgress() {
    try {
        const json = localStorage.getItem(STORAGE_KEY);
        if (!json) return null;
        
        const data = JSON.parse(json);
        console.log(`✓ 读取本地进度: cursor=${data.cursor}, records=${Object.keys(data.records || {}).length}`);
        return data;
    } catch (e) {
        console.warn('⚠ 读取本地进度失败:', e);
        return null;
    }
}

function clearLocalProgress() {
    try {
        localStorage.removeItem(STORAGE_KEY);
        console.log('✓ 本地进度已清空');
    } catch (e) {
        console.warn('⚠ 清空本地进度失败:', e);
    }
}

// ================================================================
// PiP 兼容的 DOM 访问
// ================================================================

function getDoc() {
    // 返回当前活动的 document（主页面或 PiP 窗口）
    if (state.pipWindow && !state.pipWindow.closed) {
        return state.pipWindow.document;
    }
    return document;
}

function getElement(id) {
    // PiP 兼容的 getElementById
    return getDoc().getElementById(id);
}

// ================================================================
// 初始化
// ================================================================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('测试执行器启动...');
    
    // 绑定事件
    bindEvents();
    
    // 加载会话数据
    await loadSession();
    
    // 渲染进度条
    renderProgressBar();
    
    // 渲染当前卡片
    renderCard();
    
    console.log('✓ 初始化完成');
});

// ================================================================
// 数据加载
// ================================================================

async function loadSession() {
    try {
        const resp = await fetch('/api/session');
        const data = await resp.json();
        
        state.cases = data.cases;
        state.progress = data.progress;
        
        // 优先使用本地进度
        const local = loadLocalProgress();
        if (local && local.records) {
            console.log('✓ 使用本地缓存进度');
            state.progress.records = { ...state.progress.records, ...local.records };
            state.cursor = local.cursor || 0;
            
            // 确保 cursor 不会跳过未测试的用例
            while (state.cursor < state.cases.length) {
                const caseId = state.cases[state.cursor].id;
                if (!state.progress.records[caseId]) {
                    break;  // 找到第一个未测试的
                }
                state.cursor++;
            }
        } else {
            state.cursor = data.progress.cursor || 0;
        }
        
        console.log(`✓ 加载 ${state.cases.length} 条用例，当前位置 ${state.cursor}`);
    } catch (e) {
        showError('加载失败', '无法连接到服务器', '确保 serve.py 正在运行');
        console.error(e);
    }
}

// ================================================================
// 渲染
// ================================================================

function renderProgressBar() {
    const bar = getElement('progressBar');
    bar.innerHTML = '';
    
    for (let i = 0; i < state.cases.length; i++) {
        const item = document.createElement('div');
        item.className = 'progress-item';
        
        const caseId = state.cases[i].id;
        if (state.progress.records && state.progress.records[caseId]) {
            item.classList.add('done');
        }
        if (i === state.cursor) {
            item.classList.add('current');
        }
        
        // 点击进度条跳转
        item.addEventListener('click', () => {
            state.cursor = i;
            saveLocalProgress();
            renderCard();
        });
        
        bar.appendChild(item);
    }
}

function renderCard() {
    if (state.cursor < 0 || state.cursor >= state.cases.length) {
        getElement('caseTitle').textContent = '已完成所有用例';
        getElement('caseCounter').textContent = '';
        getElement('mainActions').classList.add('hidden');
        return;
    }
    
    const testCase = state.cases[state.cursor];
    
    // 标题
    getElement('caseTitle').textContent = `${testCase.id} · ${testCase.title}`;
    getElement('caseCounter').textContent = `${state.cursor + 1} / ${state.cases.length}`;
    
    // 元信息
    const meta = getElement('caseMeta');
    meta.innerHTML = `
        <span class="tag">${testCase.side}</span>
        <span class="tag">${testCase.module}</span>
        <span class="tag">${testCase.priority}</span>
        <span class="tag">${testCase.layer}</span>
        <span class="tag">${testCase.case_type}</span>
    `;
    
    // 依据
    const req = getElement('caseRequirement');
    if (testCase.requirement) {
        req.innerHTML = `<strong>依据：</strong>${testCase.requirement}`;
        req.classList.remove('hidden');
    } else {
        req.classList.add('hidden');
    }
    
    // 前置条件
    renderList('preconditionsList', testCase.preconditions || []);
    
    // 测试数据
    renderList('testDataList', testCase.test_data || []);
    
    // 执行步骤
    renderList('stepsList', testCase.steps || []);
    
    // 预期结果
    const checkpoints = testCase.checkpoints || [];
    getElement('checkpointsTitle').textContent = `预期结果 共 ${checkpoints.length} 条`;
    const checkpointsList = getElement('checkpointsList');
    checkpointsList.innerHTML = '';
    
    checkpoints.forEach(cp => {
        const li = document.createElement('li');
        li.textContent = cp.text;
        
        // 负向断言高亮
        if (cp.flags && cp.flags.includes('negative')) {
            li.classList.add('checkpoint', 'negative');
            li.textContent += ' （负向断言）';
        }
        
        checkpointsList.appendChild(li);
    });
    
    // 标签
    const tags = getElement('caseTags');
    tags.innerHTML = '';
    
    if (testCase.blocker) {
        const tag = document.createElement('span');
        tag.className = 'tag-blocker';
        tag.textContent = `⚠️ 阻塞因素：${testCase.blocker}`;
        tags.appendChild(tag);
    }
    
    if (testCase.pending_confirms && testCase.pending_confirms.length > 0) {
        testCase.pending_confirms.forEach(pc => {
            const tag = document.createElement('span');
            tag.className = 'tag-pending';
            tag.textContent = `待确认 · ${pc}`;
            tags.appendChild(tag);
        });
    }
    
    // 显示主按钮，隐藏表单
    getElement('mainActions').classList.remove('hidden');
    getElement('failForm').classList.add('hidden');
    state.formMode = false;
    
    // 清空图片
    state.images = [];
    getElement('imagePreview').innerHTML = '';
    
    // 更新进度条
    renderProgressBar();
}

function renderList(elementId, items) {
    const list = getElement(elementId);
    list.innerHTML = '';
    
    items.forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        list.appendChild(li);
    });
}

function renderImagePreview() {
    const preview = getElement('imagePreview');
    preview.innerHTML = '';
    
    state.images.forEach((blob, index) => {
        const thumb = document.createElement('div');
        thumb.className = 'image-thumb';
        
        const img = document.createElement('img');
        img.src = URL.createObjectURL(blob);
        
        const btnRemove = document.createElement('button');
        btnRemove.className = 'btn-remove';
        btnRemove.textContent = '✕';
        btnRemove.onclick = () => {
            state.images.splice(index, 1);
            renderImagePreview();
        };
        
        thumb.appendChild(img);
        thumb.appendChild(btnRemove);
        preview.appendChild(thumb);
    });
    
    // 显示/隐藏粘贴提示
    const hint = getElement('pasteHint');
    if (state.images.length === 0) {
        hint.classList.remove('hidden');
    } else {
        hint.classList.add('hidden');
    }
}

// ================================================================
// 事件绑定
// ================================================================

function bindEvents() {
    const doc = getDoc();
    
    // 主按钮
    getElement('btnPass').onclick = () => handlePass();
    getElement('btnFail').onclick = () => showFailForm();
    getElement('btnSkip').onclick = () => handleSkip();
    
    // 表单按钮
    getElement('btnSubmit').onclick = () => handleSubmit();
    getElement('btnCancel').onclick = () => hideFailForm();
    
    // 顶栏按钮
    getElement('btnPip').onclick = () => togglePiP();
    getElement('btnHistory').onclick = () => showHistory();
    getElement('btnClear').onclick = () => clearLocalProgress();
    getElement('btnHelp').onclick = () => showHelp();
    
    // 错误栏
    getElement('btnRetry').onclick = () => retryLastSubmit();
    getElement('btnCloseError').onclick = () => hideError();
    
    // 弹窗关闭
    getElement('btnCloseHistory').onclick = () => hideHistory();
    getElement('btnCloseHelp').onclick = () => hideHelp();
    
    // 键盘事件（在正确的 document 上绑定）
    doc.addEventListener('keydown', handleKeyboard);
    
    // 粘贴事件
    doc.addEventListener('paste', handlePaste);
}

function handleKeyboard(e) {
    // 在输入框中不拦截
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') {
        if (e.key === 'Escape') {
            e.target.blur();
        }
        return;
    }
    
    // 快捷键
    if (e.key === 'Enter' && !state.submitting) {
        e.preventDefault();
        if (state.formMode) {
            handleSubmit();
        } else {
            handlePass();
        }
    } else if (e.key === 'Backspace' && !state.submitting && !state.formMode) {
        e.preventDefault();
        showFailForm();
    } else if (e.key === 'b' && e.ctrlKey && !state.submitting && !state.formMode) {
        e.preventDefault();
        handleSkip();
    } else if (e.key === 'ArrowLeft' && !state.submitting && !state.formMode) {
        e.preventDefault();
        prevCase();
    } else if (e.key === 'ArrowRight' && !state.submitting && !state.formMode) {
        e.preventDefault();
        nextCase();
    } else if (e.key === 'z' && e.ctrlKey && !state.submitting && !state.formMode) {
        e.preventDefault();
        undoLast();
    } else if (e.key === 'p' && e.ctrlKey) {
        e.preventDefault();
        togglePiP();
    } else if (e.key === 'Escape') {
        e.preventDefault();
        if (state.formMode) {
            hideFailForm();
        } else {
            hideHistory();
            hideHelp();
        }
    } else if (e.key === '?') {
        e.preventDefault();
        showHelp();
    }
}

function handlePaste(e) {
    const items = e.clipboardData.items;
    let hasImage = false;
    
    for (let item of items) {
        if (item.type.startsWith('image/')) {
            hasImage = true;
            const blob = item.getAsFile();
            
            // 检查大小
            if (blob.size > 20 * 1024 * 1024) {
                showError('图片过大', `${blob.name} 超过 20MB`, '请压缩后再粘贴');
                continue;
            }
            
            state.images.push(blob);
        }
    }
    
    if (hasImage) {
        e.preventDefault();
        
        // 如果在主态，自动展开表单
        if (!state.formMode) {
            showFailForm();
        }
        
        renderImagePreview();
    }
}

// ================================================================
// 交互逻辑
// ================================================================

function showFailForm() {
    getElement('mainActions').classList.add('hidden');
    getElement('failForm').classList.remove('hidden');
    state.formMode = true;
    
    // 聚焦到说明框
    setTimeout(() => {
        getElement('inputNote').focus();
    }, 100);
}

function hideFailForm() {
    getElement('mainActions').classList.remove('hidden');
    getElement('failForm').classList.add('hidden');
    state.formMode = false;
    
    // 清空表单
    getElement('inputNote').value = '';
    getElement('inputConsole').value = '';
    state.images = [];
    renderImagePreview();
}

function prevCase() {
    if (state.cursor > 0) {
        state.cursor--;
        renderCard();
    }
}

function nextCase() {
    if (state.cursor < state.cases.length - 1) {
        state.cursor++;
        renderCard();
    }
}

function undoLast() {
    if (state.cursor > 0) {
        state.cursor--;
        renderCard();
        console.log('↶ 撤销到上一条');
    }
}

// ================================================================
// 提交逻辑
// ================================================================

async function handlePass() {
    await submitResult('通过', '', '', []);
}

async function handleSkip() {
    if (confirm('确认跳过这条用例？（将记录为「未执行」）')) {
        await submitResult('未执行', '', '', []);
    }
}

async function handleSubmit() {
    const note = getElement('inputNote').value.trim();
    const console = getElement('inputConsole').value.trim();
    
    if (!note) {
        showError('缺少必填项', '请填写说明', '');
        getElement('inputNote').focus();
        return;
    }
    
    await submitResult('不通过', note, console, state.images);
}

async function submitResult(result, note, consoleText, images) {
    if (state.submitting) return;
    
    state.submitting = true;
    state.lastSubmit = { result, note, consoleText, images };
    
    // 显示加载
    getElement('loading').classList.remove('hidden');
    disableButtons();
    
    try {
        const formData = new FormData();
        const testCase = state.cases[state.cursor];
        
        formData.append('case_id', testCase.id);
        formData.append('result', result);
        if (note) formData.append('note', note);
        if (consoleText) formData.append('console', consoleText);
        
        // 添加图片
        images.forEach((blob, i) => {
            formData.append('images', blob, `shot-${Date.now()}-${i}.png`);
        });
        
        // touched 字段（简化版：暂不实现显式清空逻辑）
        formData.append('touched', JSON.stringify([]));
        
        const resp = await fetch('/api/submit', {
            method: 'POST',
            body: formData
        });
        
        const data = await resp.json();
        
        if (data.ok) {
            console.log(`✓ 提交成功：${testCase.id} → ${result}`);
            
            // 更新进度
            if (!state.progress.records) {
                state.progress.records = {};
            }
            state.progress.records[testCase.id] = {
                result,
                record_id: data.record_id,
                bug_record_id: data.bug_record_id
            };
            
            // 保存到本地
            saveLocalProgress();
            
            // 前进到下一条
            if (state.cursor < state.cases.length - 1) {
                state.cursor++;
            } else {
                state.cursor = state.cases.length;  // 超出范围，显示完成
            }
            
            renderCard();
            hideError();
            
            if (data.warning) {
                showError('部分成功', data.warning, '', false);
            }
        } else {
            showError('提交失败', data.error || '未知错误', data.hint || '');
        }
    } catch (e) {
        showError('网络错误', '无法连接到服务器', '确保 serve.py 正在运行');
        console.error(e);
    } finally {
        state.submitting = false;
        getElement('loading').classList.add('hidden');
        enableButtons();
    }
}

async function retryLastSubmit() {
    if (!state.lastSubmit) return;
    
    const { result, note, consoleText, images } = state.lastSubmit;
    await submitResult(result, note, consoleText, images);
}

// ================================================================
// UI 辅助
// ================================================================

function disableButtons() {
    getDoc().querySelectorAll('button').forEach(btn => {
        if (!btn.classList.contains('btn-close-error')) {
            btn.disabled = true;
        }
    });
}

function enableButtons() {
    getDoc().querySelectorAll('button').forEach(btn => {
        btn.disabled = false;
    });
}

function showError(title, message, hint, showRetry = true) {
    const bar = getElement('errorBar');
    bar.querySelector('.error-title').textContent = title;
    bar.querySelector('.error-message').textContent = message;
    bar.querySelector('.error-hint').textContent = hint;
    
    if (showRetry) {
        getElement('btnRetry').classList.remove('hidden');
    } else {
        getElement('btnRetry').classList.add('hidden');
    }
    
    bar.classList.remove('hidden');
}

function hideError() {
    getElement('errorBar').classList.add('hidden');
}

function showHistory() {
    const modal = getElement('modalHistory');
    const list = getElement('historyList');
    
    list.innerHTML = '<p style="color: var(--text-tertiary);">功能开发中...</p>';
    
    // TODO: 渲染已提交列表
    
    modal.classList.remove('hidden');
}

function hideHistory() {
    getElement('modalHistory').classList.add('hidden');
}

function showHelp() {
    getElement('modalHelp').classList.remove('hidden');
}

function hideHelp() {
    getElement('modalHelp').classList.add('hidden');
}

// ================================================================
// Document PiP
// ================================================================

async function togglePiP() {
    if (!('documentPictureInPicture' in window)) {
        alert('浏览器不支持 Document PiP 置顶功能\n\n请使用 Chrome 116+ 桌面版，或运行 start-desktop.bat 使用原生窗模式');
        return;
    }
    
    // 如果已经在 PiP，关闭它
    if (state.pipWindow && !state.pipWindow.closed) {
        state.pipWindow.close();
        state.pipWindow = null;
        return;
    }
    
    try {
        const pipWindow = await documentPictureInPicture.requestWindow({
            width: 420,
            height: 760,
            disallowReturnToOpener: true
        });
        
        state.pipWindow = pipWindow;
        
        // 复制样式到 PiP 窗口
        const linkElem = document.querySelector('link[rel="stylesheet"]');
        if (linkElem) {
            const link = pipWindow.document.createElement('link');
            link.rel = 'stylesheet';
            link.href = linkElem.href;
            pipWindow.document.head.appendChild(link);
        }
        
        // 搬运卡片到 PiP 窗口
        const app = getElement('app');
        pipWindow.document.body.appendChild(app);
        
        // 在 PiP 窗口重新绑定事件
        bindEvents();
        
        // 监听 PiP 窗口关闭，搬回主页面
        pipWindow.addEventListener('pagehide', () => {
            document.body.appendChild(app);
            state.pipWindow = null;
            // 搬回主页面后重新绑定事件
            bindEvents();
        });
        
        console.log('✓ PiP 置顶窗口已打开');
        
    } catch (e) {
        console.error('PiP 失败:', e);
        alert('置顶失败：' + e.message);
    }
}

// ================================================================
// 清空本地进度
// ================================================================

function clearLocalProgress() {
    if (!confirm('确认清空本地进度？\n\n这将删除所有本地记录的测试进度，但不影响已提交到服务器的数据。')) {
        return;
    }
    
    localStorage.removeItem('testrunner_cursor');
    localStorage.removeItem('testrunner_records');
    
    // 重置状态
    state.cursor = 0;
    state.progress.records = {};
    
    // 重新渲染
    renderProgressBar();
    renderCard();
    
    console.log('✓ 已清空本地进度');
}
