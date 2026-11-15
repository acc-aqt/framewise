// Injected into every page of the demo recording: a visible cursor, a caption bar and a
// badge for each pressed shortcut. Playwright's input never draws a cursor of its own.
(() => {
  const KEY_LABELS = {
    ArrowLeft: '←',
    ArrowRight: '→',
    ArrowUp: '↑',
    ArrowDown: '↓',
    Escape: 'Esc',
    Enter: '↵',
  };

  const style = `
    #demo-cursor {
      position: fixed; left: 0; top: 0; z-index: 2147483647; pointer-events: none;
      width: 28px; height: 28px; transform: translate(-100px, -100px);
      filter: drop-shadow(0 2px 3px rgba(0, 0, 0, 0.45));
    }
    #demo-cursor .ripple {
      position: absolute; left: -16px; top: -16px; width: 32px; height: 32px;
      border-radius: 50%; background: rgba(255, 200, 60, 0.55); opacity: 0;
    }
    #demo-cursor.clicking .ripple { animation: demo-ripple 450ms ease-out; }
    @keyframes demo-ripple {
      from { opacity: 1; transform: scale(0.3); }
      to { opacity: 0; transform: scale(1.6); }
    }
    #demo-caption {
      position: fixed; left: 50%; bottom: 28px; z-index: 2147483646; pointer-events: none;
      transform: translate(-50%, 12px); opacity: 0;
      display: flex; align-items: center; gap: 14px;
      padding: 12px 22px; border-radius: 14px;
      background: rgba(12, 12, 14, 0.86); color: #fff;
      font: 600 22px/1.2 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
      transition: opacity 200ms ease, transform 200ms ease;
    }
    #demo-caption.visible { opacity: 1; transform: translate(-50%, 0); }
    #demo-caption .via { font-weight: 400; color: rgba(255, 255, 255, 0.65); }
    #demo-keys {
      position: fixed; right: 32px; bottom: 28px; z-index: 2147483646; pointer-events: none;
      display: flex; gap: 8px;
    }
    #demo-keys kbd {
      min-width: 54px; padding: 10px 14px; border-radius: 10px; text-align: center;
      background: #fff; color: #111; border: 1px solid #ccc; border-bottom-width: 4px;
      font: 700 26px/1 -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
      animation: demo-key 900ms ease forwards;
    }
    @keyframes demo-key {
      0% { opacity: 0; transform: translateY(8px) scale(0.9); }
      12% { opacity: 1; transform: translateY(0) scale(1.06); }
      22% { transform: scale(1); }
      80% { opacity: 1; }
      100% { opacity: 0; }
    }
  `;

  const cursorSvg = `
    <svg viewBox="0 0 28 28" width="28" height="28" style="position:absolute">
      <path d="M4 2 L4 22 L9.5 17 L13 25 L16.5 23.5 L13 15.8 L20.5 15.8 Z"
        fill="#111" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/>
    </svg>
    <span class="ripple"></span>`;

  function mount() {
    if (document.getElementById('demo-cursor')) {
      return;
    }
    const sheet = document.createElement('style');
    sheet.textContent = style;
    document.head.append(sheet);

    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.innerHTML = cursorSvg;
    const caption = document.createElement('div');
    caption.id = 'demo-caption';
    const keys = document.createElement('div');
    keys.id = 'demo-keys';
    document.body.append(cursor, caption, keys);

    document.addEventListener(
      'mousemove',
      (event) => {
        cursor.style.transform = `translate(${event.clientX - 4}px, ${event.clientY - 2}px)`;
      },
      true,
    );
    document.addEventListener(
      'mousedown',
      () => {
        cursor.classList.remove('clicking');
        void cursor.offsetWidth;
        cursor.classList.add('clicking');
      },
      true,
    );
    document.addEventListener(
      'keydown',
      (event) => {
        if (['Shift', 'Alt', 'Meta', 'Control'].includes(event.key)) {
          return;
        }
        const badge = document.createElement('kbd');
        badge.textContent = KEY_LABELS[event.key] ?? event.key.toUpperCase();
        keys.append(badge);
        badge.addEventListener('animationend', () => badge.remove());
      },
      true,
    );
  }

  window.__demo = {
    caption(text, via) {
      const caption = document.getElementById('demo-caption');
      if (!text) {
        caption.classList.remove('visible');
        return;
      }
      caption.innerHTML = '';
      caption.append(document.createTextNode(text));
      if (via) {
        const hint = document.createElement('span');
        hint.className = 'via';
        hint.textContent = via;
        caption.append(hint);
      }
      caption.classList.add('visible');
    },
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount);
  } else {
    mount();
  }
})();
