from flask import Flask, request, jsonify
import subprocess
import tempfile
import os

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Java Dev Studio | Premium</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
        <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.33.0/min/vs/loader.min.js"></script>
        <style>
            :root {
                --bg: #0f172a;
                --surface: #1e293b;
                --accent: #f97316;
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
            .logo h2 { margin: 0; font-size: 1.1rem; font-weight: 700; background: linear-gradient(90deg, #f97316, #fb923c); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
            
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
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 8px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
                display: flex; align-items: center; gap: 8px;
                box-shadow: 0 4px 15px rgba(249, 115, 22, 0.4);
            }

            button:hover { transform: translateY(-2px); filter: brightness(1.1); box-shadow: 0 6px 20px rgba(249, 115, 22, 0.6); }
            button:active { transform: translateY(0); }
            button:disabled { background: #475569; cursor: not-allowed; box-shadow: none; }

            .status-badge {
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 10px;
                background: rgba(249, 115, 22, 0.1);
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
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f97316" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
            <h2>Java Cloud Studio</h2>
            <div class="status-badge">OpenJDK 17</div>
        </div>
        <div style="font-size: 11px; color: #64748b; font-weight: 500;">JAVA EPHEMERAL STACK</div>
    </header>

    <div class="main-layout">
        <div class="editor-container">
            <div id="monaco-editor"></div>
            <div class="controls">
                <button id="runBtn" onclick="runCode()">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                    RUN JAVA
                </button>
            </div>
        </div>
    </div>

    <div class="terminal-container">
        <div class="terminal-header">
            <span>Compilation & Output</span>
            <span id="exec-time"></span>
        </div>
        <div id="console-output">Initialized and ready...</div>
    </div>

    <script>
    let editor;
    require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.33.0/min/vs' }});
    require(['vs/editor/editor.main'], function() {
        editor = monaco.editor.create(document.getElementById('monaco-editor'), {
            value: [
                'public class Main {',
                '    public static void main(String[] args) {',
                '        System.out.println("🚀 Java Cloud Studio v3.0");',
                '        System.out.println("✨ Glassmorphism UI Active");',
                '        System.out.println("🔥 Compile and Run Successful");',
                '    }',
                '}'
            ].join('\\n'),
            language: 'java',
            theme: 'vs-dark',
            automaticLayout: true,
            fontSize: 14,
            fontFamily: 'Fira Code',
            minimap: { enabled: false },
            padding: { top: 20 }
        });
    });

    function runCode() {
        const code = editor.getValue();
        const outputBox = document.getElementById("console-output");
        const btn = document.getElementById("runBtn");
        const timeBox = document.getElementById("exec-time");
        
        btn.disabled = true;
        outputBox.innerHTML = "<div style='color: var(--accent);'>[SYSTEM] Compiling Main.java...</div>";
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
            outputBox.innerHTML = "<span class='error'>[FATAL] Java backend unreachable.</span>";
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
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "Main.java")
            with open(file_path, "w") as f:
                f.write(code)

            # Compile
            compile_process = subprocess.run(
                ["javac", file_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if compile_process.stderr:
                return jsonify({"error": compile_process.stderr})

            # Run
            run_process = subprocess.run(
                ["java", "-cp", tmpdir, "Main"],
                capture_output=True,
                text=True,
                timeout=30
            )

            return jsonify({
                "output": run_process.stdout[:10000],
                "error": run_process.stderr[:10000]
            })
    except subprocess.TimeoutExpired:
        return jsonify({"error": "[TIMEOUT] Execution exceeded 30s limit. Check for infinite loops!"})
    except Exception as e:
        return jsonify({"error": f"[SYSTEM ERROR] {str(e)}"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8082)
