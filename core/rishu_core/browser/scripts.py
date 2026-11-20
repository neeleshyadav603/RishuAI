"""JavaScript that Rishu runs inside pages (as strings, so packaging stays simple)."""

# Shared helpers: visible check, accessible name, role, stable test ids, row text.
# Every script runs in Rishu's isolated JavaScript world: the page's own scripts
# cannot replace these helpers (they can only change the page itself).
HELPERS = r"""
  const squash = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el || !el.getClientRects || el.getClientRects().length === 0) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || Number(st.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const roleOf = (el) => {
    const explicit = el.getAttribute('role');
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return 'link';
    if (tag === 'button' || tag === 'summary') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'input') {
      const t = (el.type || 'text').toLowerCase();
      if (['button', 'submit', 'reset', 'image'].includes(t)) return 'button';
      if (t === 'checkbox' || t === 'radio') return t;
      if (t === 'search') return 'searchbox';
      if (t === 'file') return 'file';
      return 'textbox';
    }
    if (el.isContentEditable) return 'textbox';
    return tag;
  };
  const nameOf = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria && squash(aria)) return squash(aria);
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = squash(by.split(/\s+/).map((id) => (document.getElementById(id) || {}).innerText || '').join(' '));
      if (t) return t;
    }
    if (el.id) {
      try {
        const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (l && squash(l.innerText)) return squash(l.innerText);
      } catch (e) {}
    }
    const wrap = el.closest('label');
    if (wrap && squash(wrap.innerText)) return squash(wrap.innerText).slice(0, 80);
    if (el.placeholder) return squash(el.placeholder);
    const tag = el.tagName.toLowerCase();
    if (tag !== 'input' && tag !== 'textarea' && tag !== 'select') {
      const t = squash(el.innerText);
      if (t) return t.slice(0, 80);
    } else if (tag === 'input' && ['button', 'submit'].includes((el.type || '').toLowerCase())) {
      return squash(el.value);
    }
    return squash(el.title || el.getAttribute('name') || el.getAttribute('alt') || '');
  };
  const testIds = (el) => {
    const out = {};
    for (const a of ['lexytatestid', 'testid', 'data-testid', 'data-test', 'data-qa', 'name']) {
      const v = el.getAttribute(a);
      if (v) out[a] = v;
    }
    if (el.id && !/\d{4,}|[0-9a-f]{8}-/i.test(el.id)) out.id = el.id;
    return out;
  };
  const rowOf = (el) => {
    const row = el.closest('tr, li, [role=row], [role=listitem], mat-row, .row');
    if (!row || row === el) return '';
    return squash(row.innerText).slice(0, 120);
  };
  const SELECTOR = 'a[href], button, input, textarea, select, summary, [contenteditable=""], [contenteditable=true],' +
    '[role=button], [role=tab], [role=link], [role=checkbox], [role=radio], [role=menuitem], [role=option],' +
    '[role=switch], [role=combobox], [role=textbox], [role=searchbox], [role=gridcell][tabindex]';
  const interactive = () => Array.from(document.querySelectorAll(SELECTOR)).filter(visible);
  const describe = (el) => {
    const d = {
      tag: el.tagName.toLowerCase(), role: roleOf(el), name: nameOf(el), ids: testIds(el), row: rowOf(el),
    };
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      d.type = (el.type || 'text').toLowerCase();
      if (d.type !== 'password') d.value = (el.value || '').slice(0, 60);
    }
    if (el.tagName === 'SELECT') d.value = (el.options[el.selectedIndex] || {}).text || '';
    for (const a of ['aria-selected', 'aria-checked', 'aria-pressed', 'aria-expanded']) {
      const v = el.getAttribute(a);
      if (v !== null) d[a.slice(5)] = v;
    }
    if (el.checked) d.checked = 'true';
    if (el.disabled || el.getAttribute('aria-disabled') === 'true') d.disabled = true;
    if (el.tagName === 'A') d.href = el.getAttribute('href') || '';
    return d;
  };
  const nextRef = () => {
    let max = 0;
    for (const el of document.querySelectorAll('[data-rishu-ref]')) {
      const n = parseInt((el.getAttribute('data-rishu-ref') || '').slice(1), 10);
      if (n > max) max = n;
    }
    let n = max;
    return () => 'e' + (++n);
  };
  const byRef = (ref) => document.querySelector('[data-rishu-ref="' + String(ref).replace(/"/g, '') + '"]');
  const R = { squash, visible, roleOf, nameOf, testIds, rowOf, interactive, describe, nextRef, byRef };
"""


def call(function: str, *args: object) -> str:
    """An expression that defines the helpers, then calls ``function`` with JSON args."""
    import json

    joined = ", ".join(json.dumps(arg, ensure_ascii=False) for arg in args)
    return "(() => {" + HELPERS + "; return (" + function + ")(" + joined + "); })()"


OUTLINE = r"""() => {
  const next = R.nextRef();
  const items = [];
  for (const el of R.interactive()) {
    if (items.length >= 400) break;
    let ref = el.getAttribute('data-rishu-ref');
    if (!ref) { ref = next(); el.setAttribute('data-rishu-ref', ref); }
    const d = R.describe(el);
    d.ref = ref;
    items.push(d);
  }
  const headings = Array.from(document.querySelectorAll('h1, h2, h3')).filter(R.visible)
    .map((h) => R.squash(h.innerText)).filter(Boolean).slice(0, 20);
  const text = R.squash(document.body ? document.body.innerText : '').slice(0, 4000);
  return { url: location.href, title: document.title, headings, items, text };
}"""

# Scroll an element into view and return the point to click.
POINT = r"""(ref) => {
  const el = R.byRef(ref);
  if (!el) return { found: false };
  el.scrollIntoView({ block: 'center', inline: 'center' });
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const top = document.elementFromPoint(x, y);
  return { found: true, x, y, clear: !!top && (top === el || el.contains(top) || top.contains(el)),
           info: R.describe(el) };
}"""

CLICK_FALLBACK = (
    r"""(ref) => { const el = R.byRef(ref); if (!el) return false; el.click(); return true; }"""
)

# Focus a field and select its content, so typed text replaces it.
FOCUS = r"""(ref) => {
  const el = R.byRef(ref);
  if (!el) return { found: false };
  el.scrollIntoView({ block: 'center' });
  el.focus();
  if (el.isContentEditable) { document.execCommand('selectAll', false); }
  else if (typeof el.select === 'function') { el.select(); }
  return { found: true, type: (el.type || '').toLowerCase(), tag: el.tagName.toLowerCase() };
}"""

SELECT_OPTION = r"""(ref, wanted) => {
  const el = R.byRef(ref);
  if (!el || el.tagName !== 'SELECT') return { ok: false, reason: 'not a drop-down' };
  const w = wanted.toLowerCase().trim();
  const opt = Array.from(el.options).find((o) => o.text.toLowerCase().trim() === w || o.value.toLowerCase() === w)
    || Array.from(el.options).find((o) => o.text.toLowerCase().includes(w));
  if (!opt) return { ok: false, reason: 'no such option', options: Array.from(el.options).map((o) => o.text).slice(0, 30) };
  el.value = opt.value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, chosen: opt.text };
}"""

READY = r"""() => document.readyState"""

HAS_TEXT = r"""(t) => (document.body ? document.body.innerText : '').toLowerCase().includes(t.toLowerCase())"""
