const form = document.getElementById('support-form');
const statusBox = document.getElementById('status');
const answerBox = document.getElementById('answer-box');
const answerText = document.getElementById('answer-text');
const modelName = document.getElementById('model-name');
const timeInfo = document.getElementById('time-info');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = document.getElementById('message').value.trim();
  const temperature = Number(document.getElementById('temperature').value || 0.2);
  const topP = Number(document.getElementById('top_p').value || 0.9);
  const maxTokens = Number(document.getElementById('max_tokens').value || 250);

  if (!message) {
    statusBox.textContent = 'Будь ласка, введіть звернення клієнта.';
    answerBox.classList.add('hidden');
    return;
  }

  statusBox.textContent = 'Обробка запиту...';
  answerBox.classList.add('hidden');

  try {
    const response = await fetch('/api/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        temperature,
        top_p: topP,
        max_tokens: maxTokens,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Server error');
    }

    answerText.textContent = data.answer;
    modelName.textContent = 'Модель: ' + data.model;
    timeInfo.textContent = 'Час виконання: ' + data.elapsed_seconds + ' сек';
    answerBox.classList.remove('hidden');
    statusBox.textContent = 'Готово.';
  } catch (error) {
    statusBox.textContent = error.message || 'Сталася помилка.';
  }
});
