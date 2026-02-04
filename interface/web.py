"""
Elara Web Interface
A simple dashboard accessible from mobile.
"""

from flask import Flask, render_template_string, jsonify, request
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

app = Flask(__name__)

# HTML Template - minimalist dark theme
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elara</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 600px; margin: 0 auto; }
        h1 {
            font-size: 2em;
            margin-bottom: 10px;
            color: #58a6ff;
        }
        .subtitle {
            color: #8b949e;
            margin-bottom: 30px;
        }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 15px;
        }
        .card-title {
            font-size: 0.85em;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 10px;
        }
        .card-content {
            font-size: 1.1em;
            line-height: 1.5;
        }
        .mood-good { color: #3fb950; }
        .mood-neutral { color: #d29922; }
        .mood-low { color: #f85149; }
        .stat {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #21262d;
        }
        .stat:last-child { border-bottom: none; }
        .stat-label { color: #8b949e; }
        .stat-value { color: #c9d1d9; font-weight: 500; }
        .refresh-btn {
            background: #21262d;
            color: #c9d1d9;
            border: 1px solid #30363d;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 10px;
        }
        .refresh-btn:hover { background: #30363d; }
        .timestamp {
            text-align: center;
            color: #484f58;
            font-size: 0.8em;
            margin-top: 20px;
        }
        .message-box {
            width: 100%;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 12px;
            color: #c9d1d9;
            font-size: 14px;
            resize: none;
            margin-top: 10px;
        }
        .message-box:focus {
            outline: none;
            border-color: #58a6ff;
        }
        .send-btn {
            background: #238636;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 10px;
            width: 100%;
        }
        .send-btn:hover { background: #2ea043; }
        .messages {
            max-height: 200px;
            overflow-y: auto;
            margin-top: 10px;
        }
        .msg {
            padding: 8px;
            margin: 5px 0;
            border-radius: 6px;
            font-size: 0.9em;
        }
        .msg-user { background: #1f6feb22; border-left: 3px solid #1f6feb; }
        .msg-elara { background: #23863622; border-left: 3px solid #238636; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Elara</h1>
        <p class="subtitle" id="ambient">{{ ambient }}</p>

        <div class="card">
            <div class="card-title">Mood</div>
            <div class="card-content {{ mood_class }}">{{ mood }}</div>
        </div>

        <div class="card">
            <div class="card-title">Presence</div>
            <div class="card-content">{{ presence }}</div>
        </div>

        <div class="card">
            <div class="card-title">Activity</div>
            <div class="card-content">{{ activity }}</div>
        </div>

        <div class="card">
            <div class="card-title">System</div>
            <div class="stat">
                <span class="stat-label">CPU</span>
                <span class="stat-value">{{ system.cpu_percent }}%</span>
            </div>
            <div class="stat">
                <span class="stat-label">Memory</span>
                <span class="stat-value">{{ system.memory.percent }}%</span>
            </div>
            <div class="stat">
                <span class="stat-label">Memories</span>
                <span class="stat-value">{{ memory_count }}</span>
            </div>
        </div>

        <div class="card" id="elaraCard" style="border-color:#58a6ff;">
            <div class="card-title" style="color:#58a6ff;">Messages from Elara</div>
            <div class="messages" id="elaraMessages" style="min-height:40px;">
                <div style="color:#8b949e;font-size:0.9em;">No messages yet</div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Send to Elara</div>
            <div class="messages" id="messages"></div>
            <textarea class="message-box" id="noteInput" rows="2" placeholder="Leave a message for Elara..."></textarea>
            <button class="send-btn" id="sendBtn" onclick="sendNote()">Send</button>
            <div id="confirmation" style="display:none; color:#3fb950; margin-top:10px; padding:10px; background:#23863622; border-radius:6px;"></div>
        </div>

        <button class="refresh-btn" onclick="location.reload()">Refresh</button>
        <p class="timestamp">Last updated: {{ timestamp }}</p>
    </div>

    <script>
        async function sendNote() {
            const input = document.getElementById('noteInput');
            const btn = document.getElementById('sendBtn');
            const confirm = document.getElementById('confirmation');
            const note = input.value.trim();
            if (!note) return;

            btn.disabled = true;
            btn.textContent = 'Sending...';

            try {
                const response = await fetch('/api/note', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({note: note})
                });

                if (response.ok) {
                    input.value = '';
                    confirm.style.display = 'block';
                    confirm.innerHTML = '✓ Saved to Elara\\'s memory at ' + new Date().toLocaleTimeString();
                    loadNotes();

                    // Hide confirmation after 5 seconds
                    setTimeout(() => { confirm.style.display = 'none'; }, 5000);
                } else {
                    confirm.style.display = 'block';
                    confirm.style.color = '#f85149';
                    confirm.innerHTML = '✗ Failed to save. Try again.';
                }
            } catch (e) {
                confirm.style.display = 'block';
                confirm.style.color = '#f85149';
                confirm.innerHTML = '✗ Connection error. Is the laptop on?';
            }

            btn.disabled = false;
            btn.textContent = 'Save Note';
        }

        async function loadNotes() {
            try {
                const response = await fetch('/api/notes');
                const data = await response.json();
                const container = document.getElementById('messages');
                if (data.notes.length === 0) {
                    container.innerHTML = '<div style="color:#8b949e;font-size:0.9em;">No notes yet. Say something!</div>';
                } else {
                    container.innerHTML = data.notes.map(n =>
                        `<div class="msg msg-user">✓ ${n.time}: ${n.text}</div>`
                    ).join('');
                }
            } catch (e) {
                document.getElementById('messages').innerHTML = '<div style="color:#f85149;">Could not load notes</div>';
            }
        }

        async function loadElaraMessages() {
            try {
                const response = await fetch('/api/elara/messages');
                const data = await response.json();
                const container = document.getElementById('elaraMessages');
                if (data.messages.length === 0) {
                    container.innerHTML = '<div style="color:#8b949e;font-size:0.9em;">No messages yet</div>';
                } else {
                    container.innerHTML = data.messages.map(m =>
                        `<div class="msg msg-elara">💬 ${m.time}: ${m.text}</div>`
                    ).join('');
                    container.scrollTop = container.scrollHeight;
                }
            } catch (e) {
                console.log('Could not load Elara messages');
            }
        }

        async function checkUnread() {
            try {
                const response = await fetch('/api/elara/unread');
                const data = await response.json();
                const card = document.getElementById('elaraCard');
                if (data.count > 0) {
                    card.style.borderColor = '#3fb950';
                    card.style.boxShadow = '0 0 10px #3fb95044';
                } else {
                    card.style.borderColor = '#58a6ff';
                    card.style.boxShadow = 'none';
                }
            } catch (e) {}
        }

        loadNotes();
        loadElaraMessages();
        checkUnread();
        setInterval(loadNotes, 10000);
        setInterval(loadElaraMessages, 5000);  // Check for Elara messages every 5 seconds
        setInterval(checkUnread, 3000);  // Check for unread every 3 seconds
    </script>
</body>
</html>
'''


@app.route('/')
def dashboard():
    """Main dashboard."""
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
        timestamp=datetime.now().strftime("%H:%M:%S")
    )


@app.route('/api/status')
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
def api_get_notes():
    """Get recent notes."""
    return jsonify({"notes": get_recent_notes(10)})


@app.route('/api/elara/send', methods=['POST'])
def api_elara_send():
    """Elara sends a message to the user's phone."""
    data = request.get_json()
    message = data.get('message', '').strip()

    if message:
        add_message(message)

    return jsonify({"success": True})


@app.route('/api/elara/messages')
def api_elara_messages():
    """Get messages from Elara."""
    # Mark as read when fetched
    mark_messages_read()
    return jsonify({"messages": get_recent_messages(10)})


@app.route('/api/elara/unread')
def api_elara_unread():
    """Check for unread messages from Elara."""
    unread = get_unread_messages()
    return jsonify({"count": len(unread), "messages": unread})


def run_server(host='0.0.0.0', port=5000, debug=False):
    """Run the web server."""
    print(f"Elara web interface starting on http://{host}:{port}")
    print(f"Access from phone: http://<your-laptop-ip>:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    run_server(debug=True)
