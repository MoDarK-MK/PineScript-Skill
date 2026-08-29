let editor;
let chart;
let candleSeries;
let plotLineSeries;
let currentFilePath = "indicators/my_indicator/src/my_indicator.pine";
let currentBarsData = [];
let currentPlotsData = {};
let currentDebugBarIdx = 0;
let debugInterval = null;

// Configure Monaco AMD require path
require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.38.0/min/vs' } });

// Initialize Monaco Editor
require(['vs/editor/editor.main'], function () {
    // Register Pine Script basic syntax highlighting
    monaco.languages.register({ id: 'pinescript' });
    monaco.languages.setMonarchTokensProvider('pinescript', {
        keywords: ['if', 'else', 'for', 'while', 'switch', 'var', 'varip', 'export', 'import', 'method', 'type', 'to', 'by', 'break', 'continue'],
        builtins: ['ta', 'math', 'string', 'str', 'color', 'request', 'syminfo', 'timeframe', 'strategy', 'indicator', 'library', 'input', 'plot', 'plotshape', 'plotchar', 'plotcandle', 'plotbar', 'bgcolor', 'fill', 'alert', 'alertcondition', 'barstate', 'array', 'matrix', 'map', 'box', 'line', 'label', 'table', 'polyline'],
        tokenizer: {
            root: [
                [/[a-zA-Z_]\w*/, { cases: { '@keywords': 'keyword', '@builtins': 'type.identifier', '@default': 'identifier' } }],
                [/\/\/.*/, 'comment'],
                [/".*?"/, 'string'],
                [/'.*?'/, 'string'],
                [/\d*\.\d+([eE][\-+]?\d+)?/, 'number.float'],
                [/\d+/, 'number'],
            ]
        }
    });

    // Custom dark theme matching design system
    monaco.editor.defineTheme('pine-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
            { token: 'keyword', foreground: '22C55E', fontStyle: 'bold' },
            { token: 'type.identifier', foreground: '60A5FA' },
            { token: 'comment', foreground: '64748B', fontStyle: 'italic' },
            { token: 'string', foreground: 'F59E0B' },
            { token: 'number', foreground: 'EC4899' }
        ],
        colors: {
            'editor.background': '#0F172A',
            'editor.foreground': '#F8FAFC',
            'editorLineNumber.foreground': '#475569',
            'editorLineNumber.activeForeground': '#22C55E',
            'editor.lineHighlightBackground': '#1E293B60',
            'editorIndentGuide.background': '#1E293B',
            'editorIndentGuide.activeBackground': '#334155'
        }
    });

    editor = monaco.editor.create(document.getElementById('monaco-editor'), {
        value: [
            '//@version=6',
            'strategy("EMA Trend Follower with ATR Risk", overlay = true, initial_capital = 10000, default_qty_type = strategy.percent_of_equity, default_qty_value = 10)',
            '',
            '// ————— Inputs',
            'fastLen = input.int(14, "Fast EMA Length", minval = 1, group = "Trend Parameters")',
            'slowLen = input.int(28, "Slow EMA Length", minval = 1, group = "Trend Parameters")',
            'atrLen  = input.int(14, "ATR Length", minval = 1, group = "Risk Management")',
            'atrMult = input.float(1.5, "ATR Stop Multiplier", minval = 0.5, step = 0.1, group = "Risk Management")',
            '',
            '// ————— Calculations',
            'fastEma = ta.ema(close, fastLen)',
            'slowEma = ta.ema(close, slowLen)',
            'atrVal  = ta.atr(atrLen)',
            '',
            'longCondition = ta.crossover(fastEma, slowEma)',
            'shortCondition = ta.crossunder(fastEma, slowEma)',
            '',
            '// ————— Strategy Execution',
            'if longCondition',
            '    strategy.entry("Long", strategy.long)',
            '    strategy.exit("Exit Long", from_entry = "Long", stop = close - atrVal * atrMult, limit = close + atrVal * atrMult * 2.0)',
            '',
            'if shortCondition',
            '    strategy.close("Long")',
            '',
            '// ————— Visual Overlays',
            'plot(fastEma, "Fast EMA", color = color.new(#22C55E, 0), linewidth = 2)',
            'plot(slowEma, "Slow EMA", color = color.new(#3B82F6, 0), linewidth = 2)'
        ].join('\n'),
        language: 'pinescript',
        theme: 'pine-dark',
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 14,
        fontFamily: "'JetBrains Mono', monospace"
    });

    // Keyboard shortcut Ctrl+S for Save
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, function () {
        saveCurrentFile();
    });

    // Initial setup
    initLightweightChart();
    loadWorkspaceFiles();
    initSettings();
});

// ---------------------------------------------------------------------------
// TradingView Lightweight Charts Initialization
// ---------------------------------------------------------------------------
function initLightweightChart() {
    const container = document.getElementById('lightweight-chart-container');
    if (!container) return;

    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth || 800,
        height: container.clientHeight || 230,
        layout: {
            background: { color: '#0B1120' },
            textColor: '#94A3B8',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11
        },
        grid: {
            vertLines: { color: '#1E293B' },
            horzLines: { color: '#1E293B' }
        },
        timeScale: {
            borderColor: '#1E293B',
            timeVisible: true,
            secondsVisible: false
        },
        rightPriceScale: {
            borderColor: '#1E293B'
        }
    });

    candleSeries = chart.addCandlestickSeries({
        upColor: '#22C55E',
        downColor: '#EF4444',
        borderVisible: false,
        wickUpColor: '#22C55E',
        wickDownColor: '#EF4444'
    });

    plotLineSeries = chart.addLineSeries({
        color: '#60A5FA',
        lineWidth: 2,
        title: 'Indicator'
    });

    window.addEventListener('resize', () => {
        if (chart && container) {
            chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
        }
    });
}

// ---------------------------------------------------------------------------
// Run Backtest & Chart Update (/api/run)
// ---------------------------------------------------------------------------
async function runBacktest() {
    const code = editor.getValue();
    const consoleOutput = document.getElementById('console-output');
    const loader = document.getElementById('loader');
    
    loader.style.display = 'inline-block';
    consoleOutput.innerHTML = '<span class="text-accent">Running offline simulation engine (300 bars)...</span>';
    
    try {
        const response = await fetch('/api/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, bars: 300 })
        });
        
        const data = await response.json();
        
        if (data.success && data.bars) {
            currentBarsData = data.bars;
            currentPlotsData = data.plots || {};

            // Format bars for Lightweight Charts
            const baseTime = Math.floor(Date.now() / 1000) - (data.bars.length * 3600);
            const chartBars = data.bars.map((b, i) => ({
                time: baseTime + (i * 3600),
                open: b.open,
                high: b.high,
                low: b.low,
                close: b.close
            }));

            candleSeries.setData(chartBars);

            // Update primary plot series overlay
            const plotKeys = Object.keys(data.plots);
            if (plotKeys.length > 0) {
                const firstPlot = data.plots[plotKeys[0]];
                const lineData = firstPlot.map((val, i) => ({
                    time: baseTime + (i * 3600),
                    value: (val !== null && !isNaN(val)) ? val : chartBars[i].close
                }));
                plotLineSeries.setData(lineData);
                plotLineSeries.applyOptions({ title: plotKeys[0] });
            }

            chart.timeScale().fitContent();

            // Update Scorecard Metrics
            const m = data.metrics;
            document.getElementById('m-return').textContent = `${m.total_return_pct >= 0 ? '+' : ''}${m.total_return_pct}%`;
            document.getElementById('m-return').className = `m-val ${m.total_return_pct >= 0 ? 'text-accent' : 'text-danger'}`;
            document.getElementById('m-sharpe').textContent = m.sharpe_ratio;
            document.getElementById('m-drawdown').textContent = `-${m.max_drawdown_pct}%`;
            document.getElementById('m-winrate').textContent = `${m.win_rate_pct}%`;
            document.getElementById('m-profitfactor').textContent = m.profit_factor;
            document.getElementById('m-trades').textContent = m.total_trades;

            consoleOutput.innerHTML = `<span class="text-accent">✔ Simulation complete!</span>\nBars evaluated: ${data.bars.length}\nFinal Equity: $${m.final_equity}\nTotal Trades: ${m.total_trades} (Win Rate: ${m.win_rate_pct}%)\nSharpe Ratio: ${m.sharpe_ratio}`;
            
            // Switch to Chart tab
            switchTab('chart');

            // Setup Step Debugger
            setupDebugger(data.bars, data.plots);
        } else {
            consoleOutput.innerHTML = `<span class="text-warning">Simulation Error:</span> ${data.error || 'Unknown error'}`;
        }
    } catch (err) {
        consoleOutput.innerHTML = `<span class="text-warning">API Connection Error:</span> ${err}`;
    } finally {
        loader.style.display = 'none';
    }
}

document.getElementById('btn-run-backtest').addEventListener('click', runBacktest);

// ---------------------------------------------------------------------------
// Step Debugger
// ---------------------------------------------------------------------------
function setupDebugger(bars, plots) {
    document.getElementById('dbg-total-bars').textContent = bars.length;
    currentDebugBarIdx = bars.length - 1;
    renderDebugBar(currentDebugBarIdx);
}

function renderDebugBar(idx) {
    if (!currentBarsData || currentBarsData.length === 0) return;
    if (idx < 0) idx = 0;
    if (idx >= currentBarsData.length) idx = currentBarsData.length - 1;
    currentDebugBarIdx = idx;

    document.getElementById('dbg-bar-index').textContent = idx;
    const bar = currentBarsData[idx];
    const prevBar = idx > 0 ? currentBarsData[idx - 1] : bar;

    const tbody = document.querySelector('#dbg-var-table tbody');
    tbody.innerHTML = '';

    const vars = [
        { name: 'open', type: 'float (series)', val: bar.open, prev: prevBar.open },
        { name: 'high', type: 'float (series)', val: bar.high, prev: prevBar.high },
        { name: 'low', type: 'float (series)', val: bar.low, prev: prevBar.low },
        { name: 'close', type: 'float (series)', val: bar.close, prev: prevBar.close },
        { name: 'volume', type: 'float (series)', val: bar.volume, prev: prevBar.volume }
    ];

    Object.keys(currentPlotsData).forEach(pName => {
        const pSeries = currentPlotsData[pName];
        vars.push({
            name: pName,
            type: 'plot (series)',
            val: pSeries[idx] !== null ? pSeries[idx] : 'na',
            prev: idx > 0 && pSeries[idx - 1] !== null ? pSeries[idx - 1] : 'na'
        });
    });

    vars.forEach(v => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td><b>${v.name}</b></td><td class="text-muted">${v.type}</td><td class="text-accent">${typeof v.val === 'number' ? v.val.toFixed(2) : v.val}</td><td class="text-muted">${typeof v.prev === 'number' ? v.prev.toFixed(2) : v.prev}</td>`;
        tbody.appendChild(tr);
    });
}

document.getElementById('dbg-prev').addEventListener('click', () => {
    renderDebugBar(currentDebugBarIdx - 1);
});

document.getElementById('dbg-next').addEventListener('click', () => {
    renderDebugBar(currentDebugBarIdx + 1);
});

document.getElementById('dbg-play').addEventListener('click', () => {
    if (debugInterval) {
        clearInterval(debugInterval);
        debugInterval = null;
        document.getElementById('dbg-play').innerHTML = '<i class="ph ph-play"></i> Auto Step';
    } else {
        document.getElementById('dbg-play').innerHTML = '<i class="ph ph-pause"></i> Pause';
        debugInterval = setInterval(() => {
            if (currentDebugBarIdx >= currentBarsData.length - 1) {
                clearInterval(debugInterval);
                debugInterval = null;
                document.getElementById('dbg-play').innerHTML = '<i class="ph ph-play"></i> Auto Step';
                return;
            }
            renderDebugBar(currentDebugBarIdx + 1);
        }, 200);
    }
});

// ---------------------------------------------------------------------------
// Linting & Problems Panel
// ---------------------------------------------------------------------------
async function runLint() {
    const code = editor.getValue();
    const consoleOutput = document.getElementById('console-output');
    const problemsList = document.getElementById('problems-list');
    const badgeProblems = document.getElementById('badge-problems');
    const loader = document.getElementById('loader');
    
    loader.style.display = 'inline-block';
    consoleOutput.innerHTML = '<span class="text-muted">Linting Pine Script v6...</span>';
    
    try {
        const response = await fetch('/api/lint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        
        const data = await response.json();
        
        if (data.findings) {
            badgeProblems.textContent = data.findings.length;
            const markers = [];
            problemsList.innerHTML = '';
            
            if (data.findings.length === 0) {
                problemsList.innerHTML = '<div class="text-accent p-3">✔ Clean! No errors or warnings found.</div>';
                consoleOutput.innerHTML = '<span class="text-accent">✔ Lint Passed! Code adheres to Pine Script v6 rules.</span>';
                monaco.editor.setModelMarkers(editor.getModel(), 'pinescript-lint', []);
                return;
            }

            let out = `<b>Summary:</b> ${data.findings.length} findings.\n\n`;
            
            data.findings.forEach(f => {
                const isError = f.severity === 'error';
                out += `<span class="${isError ? 'text-danger font-bold' : 'text-warning'}">[${f.code}] Line ${f.line}:</span> ${f.message}\n`;
                
                markers.push({
                    severity: isError ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
                    startLineNumber: f.line || 1,
                    startColumn: 1,
                    endLineNumber: f.line || 1,
                    endColumn: 100,
                    message: `[${f.code}] ${f.message}`
                });

                // Create problem card in problems tab
                const card = document.createElement('div');
                card.className = `problem-card ${isError ? 'error' : ''}`;
                card.innerHTML = `
                    <div class="problem-info">
                        <span class="problem-code">[${f.code}]</span>
                        <span>Line ${f.line}: ${f.message}</span>
                    </div>
                    <div class="problem-actions">
                        <button class="btn btn-sm btn-outline" onclick="explainRule('${f.code}')"><i class="ph ph-info"></i> Explain</button>
                        <button class="btn btn-sm btn-primary" onclick="fixWithAI('${f.code}', ${f.line}, '${f.message.replace(/'/g, "\\'")}')"><i class="ph ph-magic-wand"></i> Fix with AI</button>
                    </div>
                `;
                problemsList.appendChild(card);
            });
            
            consoleOutput.innerHTML = out;
            monaco.editor.setModelMarkers(editor.getModel(), 'pinescript-lint', markers);
            switchTab('problems');
        }
    } catch (err) {
        consoleOutput.innerHTML = `<span class="text-warning">Error calling lint API:</span> ${err}`;
    } finally {
        loader.style.display = 'none';
    }
}

document.getElementById('btn-lint').addEventListener('click', runLint);

// Auto-Fix
document.getElementById('btn-autofix').addEventListener('click', async () => {
    const code = editor.getValue();
    const consoleOutput = document.getElementById('console-output');
    try {
        const res = await fetch('/api/lint/fix', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        if (data.fixed_code) {
            editor.setValue(data.fixed_code);
            consoleOutput.innerHTML = `<span class="text-accent">Applied Mechanical Fixes:</span>\n${data.logs || 'Code updated.'}`;
            runLint();
        }
    } catch (err) {
        alert('Auto-fix failed: ' + err);
    }
});

// Convert v4/v5 to v6
document.getElementById('btn-convert-v6').addEventListener('click', async () => {
    const code = editor.getValue();
    const consoleOutput = document.getElementById('console-output');
    try {
        const res = await fetch('/api/convert-v6', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await res.json();
        if (data.converted_code) {
            editor.setValue(data.converted_code);
            consoleOutput.innerHTML = `<span class="text-accent">✔ Script Converted to Pine Script v6!</span>`;
            runLint();
        }
    } catch (err) {
        alert('Convert v6 failed: ' + err);
    }
});

// Explain Rule
window.explainRule = async function(code) {
    try {
        const res = await fetch(`/api/explain/${code}`);
        const data = await res.json();
        document.getElementById('modal-title').textContent = `Rule Explanation: ${code}`;
        document.getElementById('modal-text').textContent = data.explanation || data.error || 'No explanation found.';
        document.getElementById('explanation-modal').classList.add('active');
    } catch (err) {
        alert('Explain failed: ' + err);
    }
};

// Fix with AI
window.fixWithAI = function(code, line, msg) {
    const prompt = `Fix error [${code}] on line ${line}: "${msg}" in this Pine Script v6 code. Provide the complete updated code block.`;
    document.getElementById('chat-input').value = prompt;
    sendChat();
};

// ---------------------------------------------------------------------------
// File Explorer & Workspace Management
// ---------------------------------------------------------------------------
async function loadWorkspaceFiles() {
    const treeContainer = document.getElementById('file-tree');
    try {
        const res = await fetch('/api/files/list');
        const data = await res.json();
        treeContainer.innerHTML = '';

        if (!data.tree || data.tree.length === 0) {
            treeContainer.innerHTML = '<div class="p-3 text-muted">No projects found.</div>';
            return;
        }

        data.tree.forEach(cat => {
            const catEl = document.createElement('div');
            catEl.className = 'tree-category';
            catEl.innerHTML = `<div class="tree-category-title"><i class="ph ph-folder"></i> ${cat.name}</div>`;
            
            cat.children.forEach(file => {
                const fileEl = document.createElement('div');
                fileEl.className = 'tree-file';
                fileEl.innerHTML = `<i class="ph ph-file-code"></i> ${file.name}`;
                fileEl.onclick = () => openFile(file.path, file.name);
                catEl.appendChild(fileEl);
            });
            treeContainer.appendChild(catEl);
        });
    } catch (err) {
        treeContainer.innerHTML = `<div class="p-3 text-warning">Could not load files: ${err}</div>`;
    }
}

async function openFile(relPath, fileName) {
    try {
        const res = await fetch('/api/files/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: relPath })
        });
        const data = await res.json();
        if (data.content !== undefined) {
            editor.setValue(data.content);
            currentFilePath = relPath;
            document.getElementById('current-filename').textContent = fileName;
            
            // Highlight active in tree
            document.querySelectorAll('.tree-file').forEach(el => el.classList.remove('active'));
            event.target.classList.add('active');
            
            runLint();
        }
    } catch (err) {
        alert('Could not open file: ' + err);
    }
}

async function saveCurrentFile() {
    if (!currentFilePath) return;
    const content = editor.getValue();
    try {
        const res = await fetch('/api/files/write', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentFilePath, content })
        });
        const data = await res.json();
        if (data.success) {
            const consoleOutput = document.getElementById('console-output');
            consoleOutput.innerHTML += `\n<span class="text-accent">✔ Saved ${currentFilePath}</span>`;
        }
    } catch (err) {
        alert('Save failed: ' + err);
    }
}

document.getElementById('btn-save-file').addEventListener('click', saveCurrentFile);
document.getElementById('btn-refresh-files').addEventListener('click', loadWorkspaceFiles);

// ---------------------------------------------------------------------------
// Multi-Provider AI Chat
// ---------------------------------------------------------------------------
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const chatMessages = document.getElementById('chat-messages');
const providerSelect = document.getElementById('provider-select');
const modelSelect = document.getElementById('model-select');

async function updateModelsList() {
    const provider = providerSelect.value;
    try {
        const res = await fetch(`/api/models?provider=${provider}&host=${encodeURIComponent(localStorage.getItem('cfg_ollama_host') || 'http://localhost:11434')}`);
        const data = await res.json();
        modelSelect.innerHTML = '';
        (data.models || ['default']).forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            modelSelect.appendChild(opt);
        });
    } catch (err) {
        console.error(err);
    }
}

providerSelect.addEventListener('change', updateModelsList);

async function sendChat() {
    const prompt = chatInput.value.trim();
    if (!prompt) return;
    
    // User message
    const userMsg = document.createElement('div');
    userMsg.className = 'message user';
    userMsg.textContent = prompt;
    chatMessages.appendChild(userMsg);
    
    chatInput.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // AI message container
    const aiMsg = document.createElement('div');
    aiMsg.className = 'message ai';
    chatMessages.appendChild(aiMsg);

    const provider = providerSelect.value;
    const model = modelSelect.value;
    const apiKey = localStorage.getItem(`cfg_${provider}_key`) || '';
    const host = localStorage.getItem('cfg_ollama_host') || 'http://localhost:11434';
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: `Current Pine Script Code:\n\`\`\`pine\n${editor.getValue()}\n\`\`\`\n\nUser Request: ${prompt}`,
                provider,
                model,
                api_key: apiKey,
                host
            })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let done = false;
        let accumulatedText = '';
        
        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                accumulatedText += chunk;
                aiMsg.textContent = accumulatedText;
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        }
        
        // Format markdown code blocks
        if (accumulatedText.includes('```')) {
            const parts = accumulatedText.split('```');
            let formatted = '';
            for (let i = 0; i < parts.length; i++) {
                if (i % 2 === 1) {
                    const codeContent = parts[i].replace(/^pine|pinescript/, '');
                    formatted += `<pre><code>${codeContent.trim()}</code></pre>`;
                } else {
                    formatted += parts[i].replace(/\n/g, '<br>');
                }
            }
            aiMsg.innerHTML = formatted;
            
            // Add click-to-apply feature on generated code
            const preBlocks = aiMsg.querySelectorAll('pre code');
            preBlocks.forEach(codeBlock => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-primary btn-sm mt-2';
                btn.innerHTML = '<i class="ph ph-arrow-down-left"></i> Apply to Editor';
                btn.onclick = () => {
                    editor.setValue(codeBlock.textContent);
                    runLint();
                };
                codeBlock.parentElement.appendChild(btn);
            });
        }
        
    } catch (err) {
        aiMsg.textContent = `Error connecting to AI Provider (${provider}): ${err}`;
    }
}

btnSend.addEventListener('click', sendChat);
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChat();
    }
});

// Quick action chips
document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
        chatInput.value = chip.dataset.prompt;
        sendChat();
    });
});

// ---------------------------------------------------------------------------
// Tabs Switching
// ---------------------------------------------------------------------------
function switchTab(tabId) {
    document.querySelectorAll('.panel-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    const tabHeader = document.querySelector(`.panel-tab[data-tab="${tabId}"]`);
    const tabBody = document.getElementById(`tab-${tabId}`);
    if (tabHeader) tabHeader.classList.add('active');
    if (tabBody) tabBody.classList.add('active');

    if (tabId === 'chart' && chart) {
        const container = document.getElementById('lightweight-chart-container');
        if (container) chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    }
}

document.querySelectorAll('.panel-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
});

// ---------------------------------------------------------------------------
// Activity Bar Navigation
// ---------------------------------------------------------------------------
document.getElementById('act-files').addEventListener('click', () => {
    const sidebar = document.getElementById('files-sidebar');
    sidebar.style.display = sidebar.style.display === 'none' ? 'flex' : 'none';
});

document.getElementById('act-chart').addEventListener('click', () => switchTab('chart'));
document.getElementById('act-mtf').addEventListener('click', async () => {
    switchTab('mtf');
    const res = await fetch('/api/inspect-mtf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: editor.getValue() })
    });
    const data = await res.json();
    const mtfDiv = document.getElementById('mtf-results');
    if (data.timeline_visualization) {
        mtfDiv.innerHTML = `<h4>MTF Analysis for ${data.file}</h4><pre><code>${data.timeline_visualization}</code></pre>`;
    } else {
        mtfDiv.innerHTML = `<div class="text-muted">No request.security calls found in current script.</div>`;
    }
});

document.getElementById('act-designer').addEventListener('click', () => {
    document.getElementById('designer-modal').classList.add('active');
});

document.getElementById('act-webhook').addEventListener('click', () => {
    document.getElementById('webhook-modal').classList.add('active');
});

document.getElementById('act-settings').addEventListener('click', () => {
    document.getElementById('settings-modal').classList.add('active');
});

// ---------------------------------------------------------------------------
// Modals Handling
// ---------------------------------------------------------------------------
document.querySelectorAll('.close-modal').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.modal').forEach(m => m.classList.remove('active'));
    });
});

// Settings Save
function initSettings() {
    document.getElementById('cfg-ollama-host').value = localStorage.getItem('cfg_ollama_host') || 'http://localhost:11434';
    document.getElementById('cfg-openai-key').value = localStorage.getItem('cfg_openai_key') || '';
    document.getElementById('cfg-anthropic-key').value = localStorage.getItem('cfg_anthropic_key') || '';
    document.getElementById('cfg-deepseek-key').value = localStorage.getItem('cfg_deepseek_key') || '';
}

document.getElementById('btn-save-settings').addEventListener('click', () => {
    localStorage.setItem('cfg_ollama_host', document.getElementById('cfg-ollama-host').value);
    localStorage.setItem('cfg_openai_key', document.getElementById('cfg-openai-key').value);
    localStorage.setItem('cfg_anthropic_key', document.getElementById('cfg-anthropic-key').value);
    localStorage.setItem('cfg_deepseek_key', document.getElementById('cfg-deepseek-key').value);
    document.getElementById('settings-modal').classList.remove('active');
    alert('Settings saved successfully!');
});

// Visual Input Designer Logic
document.getElementById('btn-add-input-row').addEventListener('click', () => {
    const row = document.createElement('div');
    row.className = 'input-row';
    row.innerHTML = `
        <input type="text" placeholder="Title" class="form-control inp-title" value="New Parameter">
        <select class="form-control inp-type">
            <option value="int">int</option>
            <option value="float">float</option>
            <option value="bool">bool</option>
            <option value="string">string</option>
            <option value="color">color</option>
        </select>
        <input type="text" placeholder="Default" class="form-control inp-def" value="20">
        <input type="text" placeholder="Group" class="form-control inp-grp" value="Parameters">
    `;
    document.getElementById('input-rows').appendChild(row);
});

document.getElementById('btn-gen-input-code').addEventListener('click', () => {
    const rows = document.querySelectorAll('#input-rows .input-row');
    const lines = [];
    rows.forEach(r => {
        const title = r.querySelector('.inp-title').value;
        const type = r.querySelector('.inp-type').value;
        const def = r.querySelector('.inp-def').value;
        const grp = r.querySelector('.inp-grp').value;
        const varName = title.toLowerCase().replace(/[^a-zA-Z0-9]/g, '');
        lines.push(`${varName} = input.${type}(${def}, "${title}", group = "${grp}")`);
    });
    document.getElementById('generated-input-code').textContent = lines.join('\n');
});

document.getElementById('btn-insert-input-code').addEventListener('click', () => {
    const genCode = document.getElementById('generated-input-code').textContent;
    if (genCode && genCode !== '// Click Generate to preview code') {
        const pos = editor.getPosition();
        editor.executeEdits('input-designer', [{
            range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
            text: genCode + '\n'
        }]);
        document.getElementById('designer-modal').classList.remove('active');
    }
});

// Webhook Tester Logic
document.getElementById('btn-test-webhook').addEventListener('click', async () => {
    const url = document.getElementById('wh-url').value;
    const payload = document.getElementById('wh-payload').value;
    const resDiv = document.getElementById('wh-result');
    resDiv.textContent = 'Testing webhook dispatch...';
    try {
        const res = await fetch('/api/webhook/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, payload })
        });
        const data = await res.json();
        resDiv.textContent = JSON.stringify(data, null, 2);
    } catch (err) {
        resDiv.textContent = 'Error: ' + err;
    }
});
