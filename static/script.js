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

// Оновлена функція додавання повідомлень
function appendMessage(type, content) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type} animate__animated animate__fadeInUp`;
    messageDiv.innerHTML = content;
    document.getElementById('chat-messages').appendChild(messageDiv);
    scrollToBottom();
}

// Оновлена функція прокрутки
function scrollToBottom() {
    const messagesWrapper = document.querySelector('.messages-wrapper');
    if (messagesWrapper) {
        setTimeout(() => {
            messagesWrapper.scrollTo({
                top: messagesWrapper.scrollHeight,
                behavior: 'smooth'
            });
        }, 100);
    }
}