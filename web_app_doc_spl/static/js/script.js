let messageCount = 0;

function addMessage(content, type = 'user') {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}`;
    messageDiv.textContent = content;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
    messageCount++;
    if (type === 'agent' && messageCount > 1) {
        document.getElementById('connectionStatus').textContent = '✅ Connected';
    }
}

function showTyping() {
    document.getElementById('typingIndicator').style.display = 'flex';
}

function hideTyping() {
    document.getElementById('typingIndicator').style.display = 'none';
}

function setButtonState(disabled) {
    const sendButton = document.getElementById('sendButton');
    const sendButtonText = document.getElementById('sendButtonText');
    const sendButtonIcon = document.getElementById('sendButtonIcon');
    const messageInput = document.getElementById('messageInput');
    sendButton.disabled = disabled;
    sendButtonText.textContent = disabled ? 'Sending' : 'Send';
    sendButtonIcon.textContent = disabled ? '⏳' : '✨';
    messageInput.disabled = disabled;
}

async function sendMessage(event) {
    event.preventDefault();
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();
    if (!message) return;
    addMessage(message, 'user');
    messageInput.value = '';
    resetTextareaHeight();
    showTyping();
    setButtonState(true);
    var storedSessionId = sessionStorage.getItem('chatSessionId');
    if (storedSessionId) {
        sessionId = storedSessionId;
        console.log('🔄 Existing session:', sessionId);
    } else {
        sessionId = null;
    }
    try {
        const requestBody = { message: message };
        if (sessionId != null && sessionId != "null") requestBody.session_id = sessionId;

        const agentType = document.getElementById('agentSelector').value;
        let endpoint;
        if (agentType === 'doc') {
            endpoint = '/api/chat/doc';
        } else if (agentType === 'spl') {
            endpoint = '/api/chat/spl';
        } else if (agentType === 'dmgen') {
            endpoint = '/api/chat/dmgen';
        } else {
            throw new Error('Unknown agent type');
        }

        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Server error (${response.status})`);
        }

        const data = await response.json();
        if (data.session_id) sessionId = data.session_id;
        sessionStorage.setItem('chatSessionId', sessionId);
        storedSessionId = sessionStorage.getItem('chatSessionId');

        if (data.response) {
            addMessage(data.response, 'agent');
        } else {
            throw new Error('No response received from agent');
        }

    } catch (error) {
        console.error('Error:', error);
        addMessage(`❌ ${error.message}`, 'error');
        document.getElementById('connectionStatus').textContent = '⚠️ Connection Issue';
    } finally {
        hideTyping();
        setButtonState(false);
        messageInput.focus();
    }
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage(event);
    }
}

function resetTextareaHeight() {
    const textarea = document.getElementById('messageInput');
    textarea.style.height = 'auto';
    textarea.rows = 1;
}

document.getElementById('messageInput').addEventListener('input', function () {
    this.style.height = 'auto';
    const newHeight = Math.min(this.scrollHeight, 120);
    this.style.height = newHeight + 'px';
    const lineHeight = 20;
    this.rows = Math.max(1, Math.floor(newHeight / lineHeight));
});

window.addEventListener('load', () => {
    document.getElementById('messageInput').focus();
    fetch('/api/health')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'ok') {
                document.getElementById('connectionStatus').textContent = '✅ Ready';
            }
        })
        .catch(() => {
            document.getElementById('connectionStatus').textContent = '⚠️ Check Connection';
        });
});

window.addEventListener('online', () => {
    document.getElementById('connectionStatus').textContent = '🔄 Reconnecting...';
    setTimeout(() => {
        document.getElementById('connectionStatus').textContent = '✅ Connected';
    }, 1000);
});

window.addEventListener('offline', () => {
    document.getElementById('connectionStatus').textContent = '📡 Offline';
});

document.getElementById('agentSelector').addEventListener('change', (e) => {
    const chatMessages = document.getElementById('chatMessages');
    const systemMessage = document.createElement('div');
    systemMessage.className = 'message system';
    systemMessage.textContent =
        e.target.value === 'doc'
            ? "👋 Switched to Data Source Ingestion Document Agent. Give me a Data source name, I'll generate an implementation document and you can ask follow up questions."
            : e.target.value === 'spl'
                ? "👋 Switched to SPL → XQL Agent. Give me a Splunk SPL query, I'll convert to Cortex XSIAM XQL and you can ask follow up questions."
                : "👋 Switched to Data Model Generator. Give me raw logs then I'll generate data model rules for XSIAM.";
    chatMessages.appendChild(systemMessage);
    chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
});

// === New: Batch Upload Handler ===
async function uploadBatchFile(event) {
    const agentType = document.getElementById('agentSelector').value;
    let endpoint;
    if (agentType === 'doc') {
        endpoint = '/api/batch_chat/doc';
    } else if (agentType === 'spl') {
        endpoint = '/api/batch_chat/spl';
    } else if (agentType === 'dmgen') {
        endpoint = '/api/batch_chat/dmgen';
    } else {
        throw new Error('Unknown agent type');
    }
    const file = event.target.files[0];
    if (!file) return;

    addMessage(`📂 Selected file: ${file.name}`, 'system');
    addMessage(`⏳ Uploading batch file...`, 'system');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Server error (${response.status})`);
        }

        const data = await response.json();
        const statusUrl = data.status_url;

        addMessage(`✅ Batch job started! Tracking status...`, 'system');

        // Poll job status
        const interval = setInterval(async () => {
            const res = await fetch(statusUrl);
            if (!res.ok) return;
            const statusData = await res.json();

            if (statusData.status === "completed") {
                clearInterval(interval);
                const link = document.createElement('a');
                link.href = statusData.result_url;
                link.textContent = "🔗 Download Result File";
                link.target = "_blank";

                link.className = "download-link";

                addMessage(`🎉 Batch completed!`, 'system');
                const chatMessages = document.getElementById('chatMessages');
                const messageDiv = document.createElement('div');
                messageDiv.className = "message system";
                messageDiv.appendChild(link);
                chatMessages.appendChild(messageDiv);
                chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
            }
            else if (statusData.status === "failed") {
                clearInterval(interval);
                addMessage(`❌ Batch failed: ${statusData.error}`, 'error');
            }
        }, 5000); // check every 5s

    } catch (error) {
        console.error('Batch error:', error);
        addMessage(`❌ Batch failed: ${error.message}`, 'error');
    } finally {
        event.target.value = ''; // reset input
    }
}