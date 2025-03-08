function showTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = `
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <div class="typing-dot"></div>
        <span style="margin-left: 10px">Бот печатает...</span>
    `;
    document.querySelector('.chat-messages').appendChild(indicator);
}

function hideTypingIndicator() {
    const indicator = document.querySelector('.typing-indicator');
    if (indicator) indicator.remove();
}

async function sendMessage() {
    const input = document.getElementById('user-input');
    const message = input.value.trim();
    if (!message) return;

    // Очищаем ввод
    input.value = '';

    // Добавляем сообщение пользователя
    appendMessage('user', message);

    // Показываем индикатор набора
    showTypingIndicator();

    try {
        const response = await fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `message=${encodeURIComponent(message)}`
        });

        const data = await response.json();
        
        // Скрываем индикатор
        hideTypingIndicator();

        // Добавляем ответ бота
        appendMessage('bot', data.response);

        // Прокручиваем чат
        scrollToBottom();
    } catch (error) {
        console.error('Error:', error);
        hideTypingIndicator();
    }
}

function appendMessage(type, content) {
    const messagesDiv = document.querySelector('.chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;
    messageDiv.innerHTML = content.replace(/\n/g, '<br>');
    messagesDiv.appendChild(messageDiv);
}

function scrollToBottom() {
    const chatContainer = document.querySelector('.chat-container');
    chatContainer.scrollTop = chatContainer.scrollHeight;
}