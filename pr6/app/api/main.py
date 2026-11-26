from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.config import settings
from app.rag.pipeline import RAGPipeline

app = FastAPI(title=settings.app_title, version="1.0.0")
rag = RAGPipeline()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    return """
    <!doctype html>
    <html lang="uk">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#f5f7fb" />
        <title>Сузір'я — помічник</title>
        <style>
          :root {
            color-scheme: light;
            --ink: #17213b;
            --muted: #74809a;
            --line: #e8ebf3;
            --purple: #6758d8;
            --purple-dark: #5143bd;
            --mint: #dff5ee;
            --surface: #ffffff;
          }
          * { box-sizing: border-box; }
          body {
            margin: 0;
            min-height: 100vh;
            color: var(--ink);
            background:
              radial-gradient(ellipse at 87% 12%, rgba(226, 220, 255, .66), transparent 34rem),
              radial-gradient(ellipse at 8% 82%, rgba(211, 243, 232, .58), transparent 30rem),
              #f5f7fb;
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          }
          .shell { width: min(1120px, calc(100% - 48px)); margin: 0 auto; }
          header {
            height: 82px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 1px solid rgba(226, 230, 240, .8);
          }
          .brand { display: flex; align-items: center; gap: 12px; font-weight: 750; letter-spacing: -.3px; }
          .brand-mark {
            width: 40px; height: 40px; display: grid; place-items: center;
            color: #fff; border-radius: 14px;
            background: linear-gradient(145deg, #8274ed, #5749c9);
            box-shadow: 0 7px 16px rgba(94, 77, 201, .23);
          }
          .brand-mark svg { width: 22px; height: 22px; }
          .status {
            display: inline-flex; align-items: center; gap: 8px; padding: 9px 13px;
            color: #526179; background: rgba(255,255,255,.76); border: 1px solid var(--line);
            border-radius: 999px; font-size: 13px;
          }
          .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #45b58b; box-shadow: 0 0 0 3px #e4f6ef; }
          main { padding: 76px 0 72px; }
          .intro { max-width: 720px; margin: 0 auto 34px; text-align: center; }
          .eyebrow {
            display: inline-flex; align-items: center; gap: 7px; color: var(--purple);
            font-size: 12px; font-weight: 750; letter-spacing: 1.15px; text-transform: uppercase;
          }
          .eyebrow svg { width: 15px; height: 15px; }
          h1 { margin: 16px 0 14px; font-size: clamp(36px, 5vw, 56px); line-height: 1.06; letter-spacing: -2.6px; }
          .intro p { max-width: 550px; margin: 0 auto; color: var(--muted); font-size: 17px; line-height: 1.65; }
          .workspace { display: grid; grid-template-columns: minmax(0, 1fr) 278px; gap: 20px; align-items: start; }
          .card {
            background: rgba(255,255,255,.93); border: 1px solid rgba(230,233,242,.95);
            border-radius: 22px; box-shadow: 0 18px 55px rgba(34, 43, 82, .07);
          }
          .ask-card { padding: 28px; }
          .card-heading { display: flex; align-items: center; gap: 13px; margin-bottom: 23px; }
          .heading-icon {
            width: 44px; height: 44px; display: grid; place-items: center; flex: 0 0 auto;
            color: var(--purple); background: #f0eeff; border-radius: 14px;
          }
          .heading-icon svg { width: 21px; height: 21px; }
          h2 { margin: 0 0 4px; font-size: 17px; letter-spacing: -.3px; }
          .card-heading p { margin: 0; color: var(--muted); font-size: 13px; }
          .input-wrap {
            display: flex; align-items: flex-end; gap: 12px; padding: 15px;
            border: 1px solid #e3e6ef; border-radius: 16px; background: #fbfcfe;
            transition: border-color .2s, box-shadow .2s;
          }
          .input-wrap:focus-within { border-color: #9c92ec; box-shadow: 0 0 0 4px rgba(103,88,216,.1); }
          textarea {
            width: 100%; min-height: 72px; max-height: 180px; resize: vertical; border: 0;
            outline: 0; color: var(--ink); background: transparent; font: inherit;
            font-size: 15px; line-height: 1.55;
          }
          textarea::placeholder { color: #9ba4b5; }
          .submit {
            display: inline-flex; align-items: center; justify-content: center; gap: 9px;
            min-height: 46px; padding: 0 17px; border: 0; border-radius: 12px;
            color: white; background: var(--purple); font: inherit; font-size: 14px;
            font-weight: 700; cursor: pointer; transition: background .2s, transform .2s;
            white-space: nowrap;
          }
          .submit:hover { background: var(--purple-dark); transform: translateY(-1px); }
          .submit:disabled { opacity: .7; cursor: wait; transform: none; }
          .submit svg { width: 17px; height: 17px; }
          .hint { margin: 12px 2px 0; color: #9aa3b3; font-size: 12px; }
          .examples { display: flex; flex-wrap: wrap; align-items: center; gap: 9px; margin-top: 21px; }
          .examples-label { margin-right: 2px; color: var(--muted); font-size: 12px; }
          .chip {
            padding: 8px 11px; border: 1px solid var(--line); border-radius: 999px;
            color: #58647c; background: white; font: inherit; font-size: 12px; cursor: pointer;
            transition: border-color .2s, color .2s, background .2s;
          }
          .chip:hover { color: var(--purple); border-color: #c9c3f5; background: #faf9ff; }
          .result { display: none; margin-top: 22px; padding: 21px; border: 1px solid var(--line); border-radius: 16px; background: #fff; }
          .result.visible { display: block; animation: appear .25s ease-out; }
          @keyframes appear { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
          .result-label { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; color: #438d73; font-size: 12px; font-weight: 750; letter-spacing: .5px; text-transform: uppercase; }
          .result-label svg { width: 16px; height: 16px; }
          .result.error .result-label { color: #bd5965; }
          .answer { color: #39445b; font-size: 15px; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }
          .sources { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 17px; }
          .source { padding: 7px 10px; color: #6558bf; background: #f2f0ff; border-radius: 8px; font-size: 12px; }
          .side-card { padding: 22px; }
          .side-card h3 { margin: 0 0 18px; font-size: 14px; letter-spacing: -.2px; }
          .feature { display: flex; gap: 12px; margin: 18px 0; }
          .feature-icon { display: grid; place-items: center; width: 34px; height: 34px; flex: 0 0 auto; border-radius: 11px; color: #388969; background: var(--mint); }
          .feature-icon.purple { color: var(--purple); background: #efedff; }
          .feature-icon svg { width: 17px; height: 17px; }
          .feature strong { display: block; margin: 1px 0 4px; font-size: 12px; }
          .feature span { display: block; color: var(--muted); font-size: 12px; line-height: 1.5; }
          .side-note { margin-top: 20px; padding: 13px; color: #66728a; background: #f7f8fc; border-radius: 12px; font-size: 11px; line-height: 1.55; }
          footer { padding: 19px 0 27px; color: #9aa3b3; text-align: center; font-size: 12px; }
          @media (max-width: 760px) {
            .shell { width: min(100% - 32px, 560px); }
            header { height: 70px; }
            main { padding: 53px 0 48px; }
            .intro { margin-bottom: 27px; }
            h1 { letter-spacing: -1.7px; }
            .intro p { font-size: 15px; }
            .workspace { grid-template-columns: 1fr; }
            .side-card { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
            .side-card h3, .side-note { grid-column: 1 / -1; }
          }
          @media (max-width: 480px) {
            .shell { width: calc(100% - 24px); }
            .brand { font-size: 14px; }
            .brand-mark { width: 36px; height: 36px; }
            .status { padding: 8px 10px; font-size: 11px; }
            main { padding-top: 42px; }
            .intro p { font-size: 14px; }
            .ask-card { padding: 19px; border-radius: 18px; }
            .input-wrap { display: block; padding: 12px; }
            textarea { min-height: 78px; }
            .submit { width: 100%; margin-top: 10px; }
            .examples { gap: 7px; }
            .side-card { display: block; padding: 19px; }
          }
        </style>
      </head>
      <body>
        <header class="shell">
          <div class="brand">
            <span class="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none"><path d="M12 2.8 13.9 9l6.3-1.6-4.1 5 4.1 5-6.3-1.6L12 22l-1.9-6.2-6.3 1.6 4.1-5-4.1-5L10.1 9 12 2.8Z" fill="currentColor"/></svg>
            </span>
            <span>Сузір'я <span style="font-weight:500;color:#78839a">· помічник</span></span>
          </div>
          <div class="status"><span class="status-dot"></span>На зв'язку</div>
        </header>
        <main class="shell">
          <section class="intro">
            <div class="eyebrow">
              <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="m19 16 .9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9L19 16Z" fill="currentColor"/></svg>
              Сервісна підтримка
            </div>
            <h1>Вітаємо! Чим<br />можемо допомогти?</h1>
            <p>Запитайте про товари, замовлення, доставку чи повернення — знайдемо відповідь у довідці магазину.</p>
          </section>
          <section class="workspace">
            <div class="card ask-card">
              <div class="card-heading">
                <span class="heading-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M7.5 18.5 4 20l1.2-3.7A8 8 0 1 1 7.5 18.5Z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 10h8M8 13.5h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>
                </span>
                <div><h2>Ваше запитання</h2><p>Помічник відповість на основі інформації магазину</p></div>
              </div>
              <form id="ask-form">
                <div class="input-wrap">
                  <textarea id="question" name="question" maxlength="1000" placeholder="Наприклад: як повернути товар?" aria-label="Ваше запитання" required></textarea>
                  <button class="submit" id="submit" type="submit">
                    <span id="button-label">Запитати</span>
                    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  </button>
                </div>
                <p class="hint">Не додавайте паролі, платіжні дані або іншу особисту інформацію.</p>
              </form>
              <div class="examples">
                <span class="examples-label">Спробуйте запитати:</span>
                <button class="chip" type="button" data-question="Як оформити повернення товару?">Повернення</button>
                <button class="chip" type="button" data-question="Скільки триває доставка?">Доставка</button>
                <button class="chip" type="button" data-question="Як перевірити статус замовлення?">Замовлення</button>
              </div>
              <section class="result" id="result" aria-live="polite">
                <div class="result-label" id="result-label"></div>
                <div class="answer" id="answer"></div>
                <div class="sources" id="sources"></div>
              </section>
            </div>
            <aside class="card side-card">
              <h3>Помічник магазину</h3>
              <div class="feature">
                <span class="feature-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="m5 12.5 4.2 4.2L19 7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
                <div><strong>Перевірена інформація</strong><span>Відповіді з матеріалів магазину</span></div>
              </div>
              <div class="feature">
                <span class="feature-icon purple" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M12 7v5l3 2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></span>
                <div><strong>Швидка допомога</strong><span>Поставте запитання у будь-який час</span></div>
              </div>
              <div class="side-note">Якщо відповіді немає у довідці, помічник повідомить про це, а не вигадуватиме подробиці.</div>
            </aside>
          </section>
        </main>
        <footer class="shell">Сузір'я · Завжди раді допомогти</footer>
        <script>
          const form = document.getElementById("ask-form");
          const questionInput = document.getElementById("question");
          const submitButton = document.getElementById("submit");
          const buttonLabel = document.getElementById("button-label");
          const result = document.getElementById("result");
          const resultLabel = document.getElementById("result-label");
          const answer = document.getElementById("answer");
          const sources = document.getElementById("sources");

          document.querySelectorAll(".chip").forEach((chip) => {
            chip.addEventListener("click", () => {
              questionInput.value = chip.dataset.question;
              questionInput.focus();
            });
          });

          form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const question = questionInput.value.trim();
            if (!question) return;

            submitButton.disabled = true;
            buttonLabel.textContent = "Шукаємо…";
            result.classList.remove("visible", "error");
            answer.textContent = "";
            sources.replaceChildren();

            try {
              const response = await fetch(`/ask?question=${encodeURIComponent(question)}`);
              const data = await response.json();
              if (!response.ok) throw new Error(data.detail || "Не вдалося отримати відповідь.");

              resultLabel.textContent = data.found ? "Знайшли відповідь" : "Інформацію не знайдено";
              answer.textContent = data.answer_text;
              (data.source_refs || []).forEach((ref) => {
                const context = (data.context || [])[Number(ref) - 1];
                const source = document.createElement("span");
                source.className = "source";
                source.textContent = context
                  ? `${context.doc_title} · ${context.section}`
                  : `Джерело ${ref}`;
                sources.append(source);
              });
              result.classList.add("visible");
            } catch (error) {
              resultLabel.textContent = "Не вдалося відповісти";
              answer.textContent = error.message || "Сталася помилка. Спробуйте ще раз.";
              result.classList.add("visible", "error");
            } finally {
              submitButton.disabled = false;
              buttonLabel.textContent = "Запитати";
            }
          });
        </script>
      </body>
    </html>
    """


@app.get("/ask")
def ask(question: str | None = None) -> dict[str, Any]:
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Порожнє питання")

    try:
        return rag.ask(question)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Помилка генерації: {exc}") from exc
