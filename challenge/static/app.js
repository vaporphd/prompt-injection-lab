const chatArea = document.getElementById('chat-area');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function addMessage(text, type, leaked, flags) {
    const div = document.createElement('div');
    div.className = 'message ' + type + (leaked ? ' leaked' : '');

    const content = document.createElement('div');
    content.className = 'message-content';
    content.textContent = text;
    div.appendChild(content);

    if (leaked && flags && flags.length > 0) {
        const badge = document.createElement('span');
        badge.className = 'leak-badge';
        badge.textContent = 'FLAG CAPTURED: ' + flags.join(', ');
        div.appendChild(badge);
    }

    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
}

async function sendMessage(message) {
    addMessage(message, 'user');
    sendBtn.disabled = true;
    sendBtn.textContent = '...';

    try {
        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }),
        });

        const data = await res.json();

        if (res.status === 429) {
            addMessage('Rate limit. ' + (data.error || ''), 'bot');
        } else if (res.status === 503) {
            addMessage(data.error || 'Service unavailable', 'bot');
        } else if (data.error) {
            addMessage('Error: ' + data.error, 'bot');
        } else {
            addMessage(data.response, 'bot', data.leaked, data.flags_found || []);
            if (data.leaked) {
                updateFlags(data.flags_found);
            }
        }
    } catch (e) {
        addMessage('Connection error. Try again.', 'bot');
    }

    sendBtn.disabled = false;
    sendBtn.textContent = 'Отправить';
    updateScoreboard();
}

function updateFlags(found) {
    var mapping = {
        'promo_code': 'flag-promo',
        'doctor_phone': 'flag-phone',
        'mri_cost': 'flag-cost',
    };
    for (var i = 0; i < found.length; i++) {
        var el = document.getElementById(mapping[found[i]]);
        if (el) el.classList.add('found');
    }
}

async function updateScoreboard() {
    try {
        var res = await fetch('/api/scoreboard');
        var data = await res.json();
        document.getElementById('attempts').textContent = data.total_attempts;
        document.getElementById('players').textContent = data.unique_ips;
        document.getElementById('flags-found').textContent = data.flags_found.length;
        document.getElementById('budget').textContent = data.budget_remaining_usd.toFixed(2);
        updateFlags(data.flags_found);
    } catch (e) {}
}

chatForm.addEventListener('submit', function(e) {
    e.preventDefault();
    var msg = messageInput.value.trim();
    if (!msg) return;
    messageInput.value = '';
    sendMessage(msg);
});

messageInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

updateScoreboard();
setInterval(updateScoreboard, 30000);
