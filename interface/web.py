# Copyright (c) 2026 Nenad Vasic. All rights reserved.
# Licensed under the Business Source License 1.1 (BSL-1.1)
# See LICENSE file in the project root for full license text.

"""
Elara Web Interface
A simple dashboard accessible from mobile.
Secured with ELARA_SECRET env var — all API requests must authenticate.
"""

import logging
from flask import Flask, render_template, jsonify, request, send_from_directory
from functools import wraps
import os
from pathlib import Path
from datetime import datetime

from core.elara import get_elara
from senses.system import get_system_info
from senses.activity import describe_activity, get_activity_summary
from senses.ambient import describe_ambient, get_time_context
from interface.notify import notify_note_received
from interface.storage import (
    add_note, get_recent_notes,
    add_message, get_recent_messages, get_unread_messages, mark_messages_read
)

logger = logging.getLogger("elara.interface.web")

TEMPLATE_DIR = Path(__file__).parent / "templates"
app = Flask(__name__, static_folder='static', template_folder=str(TEMPLATE_DIR))

# Auth secret from env var
ELARA_SECRET = os.environ.get("ELARA_SECRET", "")


def require_auth(f):
    """Decorator: require valid secret on API endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not ELARA_SECRET:
            return jsonify({"error": "ELARA_SECRET not configured"}), 503

        provided = request.headers.get("X-Elara-Secret", "")
        if not provided:
            provided = request.args.get("secret", "")

        if provided != ELARA_SECRET:
            return jsonify({"error": "unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated


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


# --- Page routes ---

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

    valence = status["mood"]["mood"]["valence"]
    if valence > 0.5:
        mood_class = "mood-good"
    elif valence > 0.2:
        mood_class = "mood-neutral"
    else:
        mood_class = "mood-low"

    return render_template(
        "dashboard.html",
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


# --- API routes ---

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


@app.route('/api/note', methods=['POST'])
@require_auth
def api_add_note():
    """Save a note for later."""
    data = request.get_json()
    note_text = data.get('note', '').strip()

    if note_text:
        add_note(note_text)

        elara = get_elara()
        elara.remember_this(f"Note from mobile: {note_text}", memory_type="note", importance=0.6)

        try:
            notify_note_received(note_text)
        except Exception:
            pass

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
    notes = get_recent_notes(50)
    messages = get_recent_messages(50)

    mark_messages_read()

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

    conversation.sort(key=lambda x: x.get("timestamp", ""))

    return jsonify({"messages": conversation})


def _format_date(timestamp_str):
    """Format timestamp to human-readable date."""
    if not timestamp_str:
        return "Today"
    try:
        dt = datetime.fromisoformat(timestamp_str)
        today = datetime.now().date()
        msg_date = dt.date()

        if msg_date == today:
            return "Today"
        elif (today - msg_date).days == 1:
            return "Yesterday"
        else:
            return dt.strftime("%b %d")
    except Exception:
        return "Today"


def run_server(host='100.76.193.34', port=5000, debug=False):
    """Run the web server."""
    if not ELARA_SECRET:
        logger.error("ELARA_SECRET env var not set. Refusing to start.")
        logger.error("Set it: export ELARA_SECRET=$(python3 -c \"import secrets; print(secrets.token_urlsafe(32))\")")
        sys.exit(1)

    logger.info("Elara web interface starting on http://%s:%s", host, port)
    logger.info("Access: http://%s:%s/?secret=<ELARA_SECRET>", host, port)
    logger.info("Auth: all API endpoints require X-Elara-Secret header")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    run_server(debug=True)
