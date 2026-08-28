let editor;

// Initialize Monaco Editor
require(['vs/editor/editor.main'], function () {
    // Register Pine Script basic syntax highlighting
    monaco.languages.register({ id: 'pinescript' });
    monaco.languages.setMonarchTokensProvider('pinescript', {
        keywords: ['if', 'else', 'for', 'while', 'switch', 'var', 'varip', 'export', 'import', 'method'],
        builtins: ['ta', 'math', 'string', 'color', 'request', 'syminfo', 'timeframe', 'strategy', 'indicator'],
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

    editor = monaco.editor.create(document.getElementById('monaco-editor'), {
        value: [
            '//@version=6',
            'indicator("My Awesome Indicator", overlay=true)',
            '',
            '// Type your code here or ask Ollama to generate it!',
            'len = input.int(14, "Length")',
            'src = input.source(close, "Source")',
            '',
            'my_rsi = ta.rsi(src, len)',
            'plot(my_rsi, color=color.new(color.blue, 0))'
        ].join('\n'),
        language: 'pinescript',
        theme: 'vs-dark',
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 14,
        fontFamily: "'JetBrains Mono', monospace"
    });
});

// Lint functionality
document.getElementById('btn-lint').addEventListener('click', async () => {
    const code = editor.getValue();
    const consoleOutput = document.getElementById('console-output');
    const loader = document.getElementById('loader');
    
    loader.style.display = 'inline-block';
    consoleOutput.innerHTML = '<span class="text-muted">Linting...</span>';
    
    try {
        const response = await fetch('/api/lint', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        
        const data = await response.json();
        
        if (data.findings) {
            let out = `<b>Summary:</b> ${data.findings.length} findings.\n\n`;
            
            // Map findings to Monaco markers (squiggly lines)
            const markers = [];
            
            data.findings.forEach(f => {
                const isError = f.severity === 'error';
                out += `<span class="${isError ? 'text-warning' : 'text-primary'}">[${f.code}] Line ${f.line}:</span> ${f.message}\n`;
                
                markers.push({
                    severity: isError ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
                    startLineNumber: f.line || 1,
                    startColumn: 1,
                    endLineNumber: f.line || 1,
                    endColumn: 100,
                    message: `[${f.code}] ${f.message}`
                });
            });
            
            consoleOutput.innerHTML = out || '<span class="text-accent">✔ No findings! Code is clean.</span>';
            monaco.editor.setModelMarkers(editor.getModel(), 'pinescript-lint', markers);
            
        } else {
            consoleOutput.innerHTML = `<span class="text-warning">Linter output parsing failed or error occurred:</span>\n${data.raw || JSON.stringify(data)}`;
            monaco.editor.setModelMarkers(editor.getModel(), 'pinescript-lint', []);
        }
        
    } catch (err) {
        consoleOutput.innerHTML = `<span class="text-warning">Error calling API:</span> ${err}`;
    } finally {
        loader.style.display = 'none';
    }
});

// Chat functionality
const chatInput = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const chatMessages = document.getElementById('chat-messages');

async function sendChat() {
    const prompt = chatInput.value.trim();
    if (!prompt) return;
    
    // Add user message
    const userMsg = document.createElement('div');
    userMsg.className = 'message user';
    userMsg.textContent = prompt;
    chatMessages.appendChild(userMsg);
    
    chatInput.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Add empty AI message container
    const aiMsg = document.createElement('div');
    aiMsg.className = 'message ai';
    chatMessages.appendChild(aiMsg);
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt, model: 'llama3.1' })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let done = false;
        
        while (!done) {
            const { value, done: readerDone } = await reader.read();
            done = readerDone;
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                aiMsg.textContent += chunk;
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        }
        
        // Very basic markdown formatting for code blocks in chat
        if (aiMsg.textContent.includes('```')) {
            const parts = aiMsg.textContent.split('```');
            let formatted = '';
            for (let i = 0; i < parts.length; i++) {
                if (i % 2 === 1) {
                    const codeContent = parts[i].replace(/^pine|pinescript/, ''); // strip lang tag
                    formatted += `<pre><code>${codeContent.trim()}</code></pre>`;
                } else {
                    formatted += parts[i];
                }
            }
            aiMsg.innerHTML = formatted;
            
            // Add click-to-apply feature on generated code
            const preBlocks = aiMsg.querySelectorAll('pre code');
            preBlocks.forEach(codeBlock => {
                const btn = document.createElement('button');
                btn.className = 'btn btn-primary';
                btn.style.marginTop = '0.5rem';
                btn.style.padding = '0.2rem 0.5rem';
                btn.style.fontSize = '0.75rem';
                btn.innerHTML = 'Apply to Editor';
                btn.onclick = () => {
                    editor.setValue(codeBlock.textContent);
                };
                codeBlock.parentElement.appendChild(btn);
            });
        }
        
    } catch (err) {
        aiMsg.textContent = `Error connecting to Chat API: ${err}`;
    }
}

btnSend.addEventListener('click', sendChat);
chatInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendChat();
});
