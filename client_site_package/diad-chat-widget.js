/**
 * DIAD Chatbot Embed Widget for {{BUSINESS_NAME}}
 * Drop this script into your website to enable a floating AI support assistant.
 */
(function() {
  const EXTERNAL_API_URL = "{{EXTERNAL_API_URL}}";
  const BUSINESS_NAME = "{{BUSINESS_NAME}}";

  // Inject CSS styles
  const style = document.createElement('style');
  style.textContent = `
    .diad-widget-button {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: linear-gradient(135deg, #7f5af0, #2cb67d);
      box-shadow: 0 10px 25px rgba(127, 90, 240, 0.4);
      color: white;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      cursor: pointer;
      z-index: 999999;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .diad-widget-button:hover {
      transform: scale(1.1);
      box-shadow: 0 14px 30px rgba(127, 90, 240, 0.6);
    }
    .diad-widget-window {
      position: fixed;
      bottom: 96px;
      right: 24px;
      width: 380px;
      height: 560px;
      max-width: calc(100vw - 32px);
      max-height: calc(100vh - 120px);
      background: #0f172a;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 20px;
      box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
      display: none;
      flex-direction: column;
      overflow: hidden;
      z-index: 999999;
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    .diad-widget-window.open { display: flex; }
    .diad-header {
      background: linear-gradient(135deg, #1e1b4b, #0f172a);
      padding: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      color: white;
    }
    .diad-header h3 { font-size: 16px; font-weight: 700; margin: 0; }
    .diad-header p { font-size: 12px; color: #94a3b8; margin: 2px 0 0; }
    .diad-close-btn { background: none; border: none; color: #94a3b8; font-size: 20px; cursor: pointer; }
    .diad-messages { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
    .diad-msg { display: flex; gap: 8px; font-size: 14px; line-height: 1.5; }
    .diad-msg.user { flex-direction: row-reverse; }
    .diad-bubble { background: rgba(30, 41, 59, 0.8); border: 1px solid rgba(255, 255, 255, 0.08); padding: 10px 14px; border-radius: 14px; color: #f8fafc; max-width: 80%; }
    .diad-msg.user .diad-bubble { background: #7f5af0; color: white; border: none; }
    .diad-input-area { padding: 12px; border-top: 1px solid rgba(255, 255, 255, 0.1); display: flex; gap: 8px; background: rgba(15, 23, 42, 0.9); }
    .diad-input { flex: 1; background: rgba(30, 41, 59, 0.9); border: 1px solid rgba(255, 255, 255, 0.1); color: white; padding: 10px 12px; border-radius: 10px; font-size: 13px; outline: none; }
    .diad-send { background: #7f5af0; color: white; border: none; padding: 0 16px; border-radius: 10px; font-weight: 600; cursor: pointer; }
  `;
  document.head.appendChild(style);

  // Create Widget DOM
  const btn = document.createElement('div');
  btn.className = 'diad-widget-button';
  btn.innerHTML = '💬';
  btn.title = `Chat with ${BUSINESS_NAME} AI Support`;

  const win = document.createElement('div');
  win.className = 'diad-widget-window';
  win.innerHTML = `
    <div class="diad-header">
      <div>
        <h3>${escapeHtml(BUSINESS_NAME)}</h3>
        <p>AI Support Assistant</p>
      </div>
      <button class="diad-close-btn">&times;</button>
    </div>
    <div class="diad-messages" id="diadWidgetMsgs">
      <div class="diad-msg bot">
        <div class="diad-bubble">Hello! Welcome to <strong>${escapeHtml(BUSINESS_NAME)}</strong> support. How can I help you today with your order or questions?</div>
      </div>
    </div>
    <div class="diad-input-area">
      <input type="text" id="diadWidgetInput" class="diad-input" placeholder="Ask about orders, returns..." />
      <button id="diadWidgetSend" class="diad-send">Send</button>
    </div>
  `;

  document.body.appendChild(btn);
  document.body.appendChild(win);

  // Event Listeners
  btn.onclick = () => win.classList.toggle('open');
  win.querySelector('.diad-close-btn').onclick = () => win.classList.remove('open');

  const inputEl = win.querySelector('#diadWidgetInput');
  const sendBtn = win.querySelector('#diadWidgetSend');
  const msgsEl = win.querySelector('#diadWidgetMsgs');

  async function handleSend() {
    const text = inputEl.value.trim();
    if (!text) return;

    appendMsg('user', text);
    inputEl.value = '';

    const loadingId = appendMsg('bot', 'Checking...');

    const configured = EXTERNAL_API_URL;
    const urlsToTry = [];
    if (configured && !configured.includes('{{') && configured.startsWith('http')) {
      const fullUrl = configured.endsWith('/external/chat') ? configured : (configured.replace(/\/+$/, '') + '/external/chat');
      urlsToTry.push(fullUrl);
    }
    if (window.location.protocol.startsWith('http') && !urlsToTry.includes('/external/chat')) {
      urlsToTry.push('/external/chat');
    }
    if (!urlsToTry.includes('http://localhost:8000/external/chat')) {
      urlsToTry.push('http://localhost:8000/external/chat');
    }
    if (!urlsToTry.includes('http://127.0.0.1:8000/external/chat')) {
      urlsToTry.push('http://127.0.0.1:8000/external/chat');
    }

    let success = false;
    for (const ep of urlsToTry) {
      try {
        const res = await fetch(ep, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: text })
        });
        if (!res.ok) continue;
        const data = await res.json();
        updateMsg(loadingId, data.answer || data.response || "Thank you for reaching out.");
        success = true;
        break;
      } catch (err) {
        // try next fallback
      }
    }
    if (!success) {
      updateMsg(loadingId, "Connection error. Please verify your DIAD server is running at http://localhost:8000.");
    }
  }

  sendBtn.onclick = handleSend;
  inputEl.onkeypress = (e) => { if (e.key === 'Enter') handleSend(); };

  function appendMsg(role, text) {
    const id = 'diad-m-' + Date.now();
    const div = document.createElement('div');
    div.className = `diad-msg ${role}`;
    div.id = id;
    div.innerHTML = `<div class="diad-bubble">${escapeHtml(text)}</div>`;
    msgsEl.appendChild(div);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return id;
  }

  function updateMsg(id, text) {
    const el = msgsEl.querySelector('#' + id);
    if (el) el.querySelector('.diad-bubble').innerHTML = escapeHtml(text);
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");
  }
})();
