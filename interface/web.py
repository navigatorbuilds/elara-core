"""
Elara Web Interface
A simple dashboard accessible from mobile.
Secured with ELARA_SECRET env var — all API requests must authenticate.
"""

from flask import Flask, render_template_string, jsonify, request, send_from_directory
from functools import wraps
import os
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.elara import get_elara
from senses.system import get_system_info, describe_system
from senses.activity import describe_activity, get_activity_summary
from senses.ambient import describe_ambient, get_time_context
from interface.notify import notify_note_received
from interface.storage import (
    add_note, get_recent_notes,
    add_message, get_recent_messages, get_unread_messages, mark_messages_read
)

app = Flask(__name__, static_folder='static')

# Auth secret from env var
ELARA_SECRET = os.environ.get("ELARA_SECRET", "")


def require_auth(f):
    """Decorator: require valid secret on API endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ELARA_SECRET:
            # No secret configured = deny all (fail secure)
            return jsonify({"error": "ELARA_SECRET not configured"}), 503

        # Check header first, then query param
        provided = request.headers.get("X-Elara-Secret", "")
        if not provided:
            provided = request.args.get("secret", "")

        if provided != ELARA_SECRET:
            return jsonify({"error": "unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated

# HTML Template - Chat interface
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#0d1117">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Elara">
    <link rel="manifest" href="/static/manifest.json">
    <link rel="icon" href="/static/icon.svg" type="image/svg+xml">
    <link rel="apple-touch-icon" href="/static/icon.svg">
    <title>Elara</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        /* Header */
        .header {
            background: #161b22;
            border-bottom: 1px solid #30363d;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
            flex-shrink: 0;
        }

        .avatar {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            overflow: hidden;
        }

        .avatar img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .header-info {
            flex: 1;
        }

        .header-name {
            font-weight: 600;
            font-size: 16px;
            color: #f0f6fc;
        }

        .header-status {
            font-size: 12px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #3fb950;
        }

        .status-dot.away { background: #d29922; }
        .status-dot.offline { background: #484f58; }

        .mood-good { color: #3fb950; }
        .mood-neutral { color: #d29922; }
        .mood-low { color: #f85149; }

        .header-toggle {
            background: none;
            border: none;
            color: #8b949e;
            font-size: 20px;
            cursor: pointer;
            padding: 8px;
        }

        /* Status panel (collapsible) */
        .status-panel {
            background: #161b22;
            border-bottom: 1px solid #30363d;
            padding: 0;
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease, padding 0.3s ease;
        }

        .status-panel.open {
            max-height: 200px;
            padding: 12px 16px;
        }

        .status-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }

        .status-item {
            text-align: center;
        }

        .status-label {
            font-size: 10px;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .status-value {
            font-size: 14px;
            font-weight: 500;
            margin-top: 2px;
        }

        /* Chat area */
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .message {
            max-width: 80%;
            padding: 10px 14px;
            border-radius: 18px;
            font-size: 15px;
            line-height: 1.4;
            word-wrap: break-word;
        }

        .message.elara {
            background: #238636;
            color: #fff;
            align-self: flex-start;
            border-bottom-left-radius: 4px;
        }

        .message.user {
            background: #1f6feb;
            color: #fff;
            align-self: flex-end;
            border-bottom-right-radius: 4px;
        }

        .message-time {
            font-size: 11px;
            color: #8b949e;
            margin-top: 4px;
            padding: 0 14px;
        }

        .message-time.elara { align-self: flex-start; }
        .message-time.user { align-self: flex-end; }

        .chat-empty {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #484f58;
            text-align: center;
            padding: 40px;
        }

        /* Input area */
        .input-area {
            background: #161b22;
            border-top: 1px solid #30363d;
            padding: 12px 16px;
            display: flex;
            gap: 10px;
            flex-shrink: 0;
        }

        .message-input {
            flex: 1;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 20px;
            padding: 10px 16px;
            color: #c9d1d9;
            font-size: 15px;
            outline: none;
            resize: none;
            max-height: 100px;
        }

        .message-input:focus {
            border-color: #58a6ff;
        }

        .message-input::placeholder {
            color: #484f58;
        }

        .send-button {
            background: #238636;
            border: none;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            color: white;
            font-size: 18px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }

        .send-button:disabled {
            background: #21262d;
            color: #484f58;
        }

        .send-button:hover:not(:disabled) {
            background: #2ea043;
        }

        /* Date separator */
        .date-separator {
            text-align: center;
            color: #484f58;
            font-size: 12px;
            padding: 16px 0 8px 0;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="avatar"><img src="/static/avatar.jpg" alt="Elara"></div>
        <div class="header-info">
            <div class="header-name">Elara</div>
            <div class="header-status">
                <span class="status-dot"></span>
                <span id="moodText" class="{{ mood_class }}">{{ mood }}</span>
            </div>
        </div>
        <button class="header-toggle" onclick="toggleStatus()">☰</button>
    </div>

    <div class="status-panel" id="statusPanel">
        <div class="status-grid">
            <div class="status-item">
                <div class="status-label">CPU</div>
                <div class="status-value">{{ system.cpu_percent }}%</div>
            </div>
            <div class="status-item">
                <div class="status-label">Memory</div>
                <div class="status-value">{{ system.memory.percent }}%</div>
            </div>
            <div class="status-item">
                <div class="status-label">Memories</div>
                <div class="status-value">{{ memory_count }}</div>
            </div>
        </div>
    </div>

    <div class="chat-empty" id="chatEmpty">
        Start a conversation...
    </div>
    <div class="chat-container" id="chatContainer">
    </div>

    <div class="input-area">
        <textarea class="message-input" id="messageInput" rows="1" placeholder="Message Elara..." onkeydown="handleKeydown(event)"></textarea>
        <button class="send-button" id="sendButton" onclick="sendMessage()">↑</button>
    </div>
    <div id="debug" style="font-size:10px;color:#484f58;text-align:center;padding:4px;">Loading...</div>

    <script>
        const ELARA_SECRET = '{{ secret }}';
        const authHeaders = {'X-Elara-Secret': ELARA_SECRET};
        let lastMessageHash = '';

        function toggleStatus() {
            document.getElementById('statusPanel').classList.toggle('open');
        }

        function handleKeydown(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        }

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const btn = document.getElementById('sendButton');
            const text = input.value.trim();
            if (!text) return;

            btn.disabled = true;
            input.disabled = true;

            try {
                const response = await fetch('/api/note', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', ...authHeaders},
                    body: JSON.stringify({note: text})
                });

                if (response.ok) {
                    input.value = '';
                    input.style.height = 'auto';
                    // Small delay then reload to show sent message
                    setTimeout(() => loadConversation(true), 100);
                }
            } catch (e) {
                console.error('Send failed:', e);
                alert('Send failed - check connection');
            }

            btn.disabled = false;
            input.disabled = false;
            input.focus();
        }

        async function loadConversation(forceUpdate = false) {
            try {
                const response = await fetch('/api/conversation', {headers: authHeaders});
                const data = await response.json();
                const container = document.getElementById('chatContainer');
                const debug = document.getElementById('debug');

                if (!container) {
                    if (debug) debug.textContent = 'Error: no chat container';
                    return;
                }

                const empty = document.getElementById('chatEmpty');
                if (data.messages.length === 0) {
                    if (empty) empty.style.display = 'flex';
                    container.innerHTML = '';
                    if (debug) debug.textContent = 'No messages yet';
                    return;
                }

                if (empty) empty.style.display = 'none';

                // Create hash to detect changes
                const newHash = JSON.stringify(data.messages.map(m => m.timestamp));

                // Only update if content changed or forced
                if (newHash === lastMessageHash && !forceUpdate) {
                    return;
                }

                // Build chat HTML
                let html = '';
                let lastDate = '';

                data.messages.forEach(msg => {
                    // Date separator
                    const msgDate = msg.date || 'Today';
                    if (msgDate !== lastDate) {
                        html += `<div class="date-separator">${msgDate}</div>`;
                        lastDate = msgDate;
                    }

                    // Message bubble
                    const cls = msg.from === 'elara' ? 'elara' : 'user';
                    html += `<div class="message ${cls}">${escapeHtml(msg.text)}</div>`;
                    html += `<div class="message-time ${cls}">${msg.time}</div>`;
                });

                container.innerHTML = html;
                container.scrollTop = container.scrollHeight;
                lastMessageHash = newHash;

                // Debug info
                if (debug) {
                    const now = new Date().toLocaleTimeString();
                    debug.textContent = `Updated: ${now} | Msgs: ${data.messages.length}`;
                }
            } catch (e) {
                console.error('Load failed:', e);
                const debug = document.getElementById('debug');
                if (debug) debug.textContent = `Error: ${e.message}`;
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Init function
        function init() {
            const debug = document.getElementById('debug');
            if (debug) debug.textContent = 'Starting...';

            // Auto-resize textarea
            const input = document.getElementById('messageInput');
            if (input) {
                input.addEventListener('input', function() {
                    this.style.height = 'auto';
                    this.style.height = Math.min(this.scrollHeight, 100) + 'px';
                });
            }

            // Initial load and polling (1.5s for snappier feel)
            loadConversation(true);
            setInterval(loadConversation, 1500);

            // Register service worker for PWA
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/sw.js')
                    .then(() => console.log('SW registered'))
                    .catch((err) => console.log('SW registration failed:', err));
            }
        }

        // Run init when ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
        } else {
            // DOM already loaded, run now
            init();
        }
    </script>
</body>
</html>
'''


@app.route('/sw.js')
def service_worker():
    """Serve service worker from root for proper scope."""
    return send_from_directory(app.static_folder, 'sw.js', mimetype='application/javascript')


@app.after_request
def add_header(response):
    """Prevent caching for all dynamic content."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/')
def dashboard():
    """Main dashboard. Requires ?secret= query param."""
    if not ELARA_SECRET:
        return "ELARA_SECRET not configured on server", 503

    provided = request.args.get("secret", "")
    if provided != ELARA_SECRET:
        return "Unauthorized. Use ?secret=YOUR_SECRET", 401

    elara = get_elara()
    status = elara.status()

    # Determine mood class
    valence = status["mood"]["mood"]["valence"]
    if valence > 0.5:
        mood_class = "mood-good"
    elif valence > 0.2:
        mood_class = "mood-neutral"
    else:
        mood_class = "mood-low"

    return render_template_string(
        DASHBOARD_HTML,
        mood=status["mood_description"],
        mood_class=mood_class,
        presence=describe_activity(),
        activity=describe_ambient(),
        system=get_system_info(),
        memory_count=status["memory_count"],
        ambient=describe_ambient(),
        timestamp=datetime.now().strftime("%H:%M:%S"),
        secret=ELARA_SECRET,
    )


@app.route('/api/status')
@require_auth
def api_status():
    """API endpoint for status."""
    elara = get_elara()
    return jsonify({
        "status": elara.status(),
        "activity": get_activity_summary(),
        "system": get_system_info(),
        "time": get_time_context()
    })


# Storage is now persistent via interface/storage.py


@app.route('/api/note', methods=['POST'])
@require_auth
def api_add_note():
    """Save a note for later."""
    data = request.get_json()
    note_text = data.get('note', '').strip()

    if note_text:
        # Save to persistent storage
        add_note(note_text)

        # Also save to Elara's memory
        elara = get_elara()
        elara.remember_this(f"Note from mobile: {note_text}", memory_type="note", importance=0.6)

        # Send desktop notification
        try:
            notify_note_received(note_text)
        except Exception:
            pass  # Don't fail if notification fails

    return jsonify({"success": True})


@app.route('/api/notes')
@require_auth
def api_get_notes():
    """Get recent notes."""
    return jsonify({"notes": get_recent_notes(10)})


@app.route('/api/elara/send', methods=['POST'])
@require_auth
def api_elara_send():
    """Elara sends a message to the user's phone."""
    data = request.get_json()
    message = data.get('message', '').strip()

    if message:
        add_message(message)

    return jsonify({"success": True})


@app.route('/api/elara/messages')
@require_auth
def api_elara_messages():
    """Get messages from Elara."""
    # Mark as read when fetched
    mark_messages_read()
    return jsonify({"messages": get_recent_messages(10)})


@app.route('/api/elara/unread')
@require_auth
def api_elara_unread():
    """Check for unread messages from Elara."""
    unread = get_unread_messages()
    return jsonify({"count": len(unread), "messages": unread})


@app.route('/api/conversation')
@require_auth
def api_conversation():
    """Get merged conversation (notes + messages) sorted by time."""
    from datetime import datetime

    notes = get_recent_notes(50)
    messages = get_recent_messages(50)

    # Mark messages as read when viewing conversation
    mark_messages_read()

    # Merge into conversation format
    conversation = []

    for note in notes:
        conversation.append({
            "from": "user",
            "text": note["text"],
            "time": note["time"],
            "timestamp": note.get("timestamp", ""),
            "date": _format_date(note.get("timestamp"))
        })

    for msg in messages:
        conversation.append({
            "from": "elara",
            "text": msg["text"],
            "time": msg["time"],
            "timestamp": msg.get("timestamp", ""),
            "date": _format_date(msg.get("timestamp"))
        })

    # Sort by timestamp
    conversation.sort(key=lambda x: x.get("timestamp", ""))

    return jsonify({"messages": conversation})


def _format_date(timestamp_str):
    """Format timestamp to human-readable date."""
    if not timestamp_str:
        return "Today"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(timestamp_str)
        today = datetime.now().date()
        msg_date = dt.date()

        if msg_date == today:
            return "Today"
        elif (today - msg_date).days == 1:
            return "Yesterday"
        else:
            return dt.strftime("%b %d")
    except:
        return "Today"


def run_server(host='100.76.193.34', port=5000, debug=False):
    """Run the web server."""
    if not ELARA_SECRET:
        print("ERROR: ELARA_SECRET env var not set. Refusing to start.")
        print("Set it: export ELARA_SECRET=$(python3 -c \"import secrets; print(secrets.token_urlsafe(32))\")")
        sys.exit(1)

    print(f"Elara web interface starting on http://{host}:{port}")
    print(f"Access: http://{host}:{port}/?secret=<ELARA_SECRET>")
    print(f"Auth: all API endpoints require X-Elara-Secret header")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    run_server(debug=True)
