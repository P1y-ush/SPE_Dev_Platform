from flask import Flask, request, jsonify
import subprocess
import tempfile

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Flask Dev IDE | Premium</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
        <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.33.0/min/vs/loader.min.js"></script>
        <style>
            :root {
                --bg: #0f172a;
                --surface: #1e293b;
                --accent: #38bdf8;
                --success: #22c55e;
                --error: #ef4444;
                --text: #f8fafc;
                --sidebar: #020617;
            }

            body {
                background: var(--bg);
                color: var(--text);
                font-family: 'Inter', sans-serif;
                margin: 0;
                display: flex;
                flex-direction: column;
                height: 100vh;
                overflow: hidden;
            }

            header {
                background: rgba(30, 41, 59, 0.7);
                backdrop-filter: blur(12px);
                padding: 0.75rem 1.5rem;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                display: flex;
                align-items: center;
                justify-content: space-between;
                z-index: 100;
            }

            .logo { display: flex; align-items: center; gap: 10px; }
            .logo h2 { margin: 0; font-size: 1.1rem; font-weight: 700; background: linear-gradient(90deg, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            
            .main-layout {
                display: flex;
                flex-grow: 1;
                overflow: hidden;
            }

            .editor-container {
                flex-grow: 1;
                display: flex;
                flex-direction: column;
                position: relative;
            }

            #monaco-editor {
                flex-grow: 1;
            }

            .terminal-container {
                height: 35%;
                background: var(--sidebar);
                border-top: 1px solid rgba(255,255,255,0.1);
                display: flex;
                flex-direction: column;
            }

            .terminal-header {
                padding: 8px 16px;
                background: rgba(255,255,255,0.03);
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: #64748b;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }

            #console-output {
                flex-grow: 1;
                padding: 1rem;
                font-family: 'Fira Code', monospace;
                font-size: 13px;
                color: #94a3b8;
                overflow-y: auto;
                white-space: pre-wrap;
                line-height: 1.5;
            }

            .controls {
                position: absolute;
                bottom: 20px;
                right: 30px;
                display: flex;
                gap: 12px;
                z-index: 10;
            }

            button {
                background: var(--accent);
                color: var(--bg);
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 8px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                gap: 8px;
                box-shadow: 0 4px 15px rgba(56, 189, 248, 0.4);
            }

            button:hover { transform: translateY(-2px); filter: brightness(1.1); box-shadow: 0 6px 20px rgba(56, 189, 248, 0.6); }
            button:active { transform: translateY(0); }
            button:disabled { background: #475569; cursor: not-allowed; box-shadow: none; }

            .status-badge {
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 10px;
                background: rgba(56, 189, 248, 0.1);
                color: var(--accent);
            }

            .success { color: var(--success); }
            .error { color: var(--error); }
            
            ::-webkit-scrollbar { width: 8px; }
            ::-webkit-scrollbar-track { background: transparent; }
            ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
        </style>
    </head>
    <body>

    <header>
        <div class="logo">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
            <h2>Flask Cloud Studio</h2>
            <div class="status-badge" id="runtime-status">Python 3.10</div>
        </div>
        <div style="font-size: 11px; color: #64748b; font-weight: 500;">EPHEMERAL INSTANCE v3.0</div>
    </header>

    <div class="main-layout">
        <div class="editor-container">
            <div id="monaco-editor"></div>
            <div class="controls">
                <button id="runBtn" onclick="runCode()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                    EXECUTE
                </button>
            </div>
        </div>
    </div>

    <div class="terminal-container">
        <div class="terminal-header">
            <span>Integrated Terminal</span>
            <span id="exec-time"></span>
        </div>
        <div id="console-output">Ready for instruction...</div>
    </div>

    <script>
    let editor;
    require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.33.0/min/vs' }});
    require(['vs/editor/editor.main'], function() {
        editor = monaco.editor.create(document.getElementById('monaco-editor'), {
            value: [
                '# Flask Development Environment',
                '# Real-time execution enabled',
                '',
                'def welcome():',
                '    print("🚀 Flask Cloud Studio v3.0 initialized")',
                '    print("✨ Glassmorphism UI Active")',
                '    print("🔥 Multi-stack Provisioning Success")',
                '',
                'welcome()'
            ].join('\\n'),
            language: 'python',
            theme: 'vs-dark',
            automaticLayout: true,
            fontSize: 14,
            fontFamily: 'Fira Code',
            minimap: { enabled: false },
            padding: { top: 20 },
            scrollbar: {
                vertical: 'hidden',
                horizontal: 'hidden'
            }
        });
    });

    function runCode() {
        const code = editor.getValue();
        const outputBox = document.getElementById("console-output");
        const btn = document.getElementById("runBtn");
        const timeBox = document.getElementById("exec-time");
        
        btn.disabled = true;
        outputBox.innerHTML = "<div style='color: var(--accent);'>[SYSTEM] Initializing Python runtime...</div>";
        timeBox.innerText = "";

        const start = Date.now();

        fetch("/run", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({code})
        })
        .then(res => res.json())
        .then(data => {
            const end = Date.now();
            timeBox.innerText = ((end - start) / 1000).toFixed(2) + "s";
            btn.disabled = false;

            if (data.error) {
                outputBox.innerHTML = "<span class='error'>" + data.error + "</span>";
            } else {
                outputBox.innerHTML = "<span class='success'>" + (data.output || "Program finished with no output.") + "</span>";
            }
        }).catch(err => {
            btn.disabled = false;
            outputBox.innerHTML = "<span class='error'>[FATAL] Connection to cluster lost.</span>";
        });
    }
    </script>
    </body>
    </html>
    """

@app.route('/run', methods=['POST'])
def run():
    try:
        code = request.json.get("code")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(code.encode())
            filename = f.name

        result = subprocess.run(
            ["python3", filename],
            capture_output=True,
            text=True,
            timeout=30
        )

        return jsonify({
            "output": result.stdout.strip()[:10000],
            "error": result.stderr.strip()[:10000]
        })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "[TIMEOUT] Execution exceeded 30s limit. Check for infinite loops!"})
    except Exception as e:
        return jsonify({"error": f"[SYSTEM ERROR] {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
