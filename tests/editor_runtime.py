"""Editor page interaction runtime."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

# === Runtime ===

RUNTIME = r"""
const vm = require('node:vm');
const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const requests = [];
const focusLog = [];
const storageWrites = [];
const elements = new Map();
let nextResponse = 0;

/** Record one browser storage. */
function storageArea(initial) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key) => (data.has(String(key)) ? data.get(String(key)) : null),
    setItem: (key, value) => {
      data.set(String(key), String(value));
      storageWrites.push([String(key), String(value)]);
    },
    removeItem: (key) => {
      data.delete(String(key));
    },
  };
}

const pageStorage = storageArea(input.storage ?? {});

/** Represent page elements. */
class Element {
  /** Initialize observed state. */
  constructor(id = '') {
    this.id = id;
    this.children = [];
    this._value = '';
    this.textContent = '';
    this._className = '';
    this.hidden = false;
    this.disabled = false;
    this._scrollTop = 0;
    this.inViewport = true;
    this.selectionStart = undefined;
    this.selectionEnd = undefined;
    this.attributes = {};
    this.listeners = {};
  }
  /** Read current draft. */
  get value() { return this._value; }
  /** Replace native selection. */
  set value(text) {
    this._value = text;
    this.selectionStart = this.selectionEnd = text.length;
  }
  /** Read current classes. */
  get className() { return this._className; }
  /** Apply fixture layout. */
  set className(text) {
    const wasFocused = this._className.includes('editor-focus');
    this._className = text;
    if (this.id === 'workspace' && input.geometry) {
      const editor = elements.get('chat-input');
      if (editor) {
        editor.scrollTop = editor.scrollTop;
        if (input.geometry.relocate && !wasFocused && text.includes('editor-focus')) {
          editor.inViewport = false;
        }
      }
    }
  }
  /** Read fixture height. */
  get clientHeight() {
    if (!input.geometry) return 0;
    const classes = elements.get('workspace').className;
    const mode = classes.includes('editor-focus') ? 'focused'
      : classes.includes('editor-expanded') ? 'expanded' : 'normal';
    return input.geometry[mode];
  }
  /** Read fixture content. */
  get scrollHeight() { return input.geometry ? input.geometry.scrollHeight : 0; }
  /** Read viewing position. */
  get scrollTop() { return this._scrollTop; }
  /** Clamp native scrolling. */
  set scrollTop(top) {
    const next = input.geometry && this.id === 'chat-input'
      ? Math.min(Math.max(0, top), Math.max(0, this.scrollHeight - this.clientHeight))
      : top;
    const changed = this._scrollTop !== next;
    this._scrollTop = next;
    if (changed && this.listeners.scroll) {
      setTimeout(() => this.listeners.scroll({target: this}), 0);
    }
  }
  /** Record appended children. */
  append(...children) { this.children.push(...children); }
  /** Replace visible children. */
  replaceChildren(...children) { this.children = children; }
  /** Read element attributes. */
  getAttribute(name) { return this.attributes[name] ?? null; }
  /** Set element attributes. */
  setAttribute(name, value) { this.attributes[name] = String(value); }
  /** Record event listeners. */
  addEventListener(name, callback) { this.listeners[name] = callback; }
  /** Record focus targets. */
  focus(options = {}) {
    focusLog.push(this.id);
    document.activeElement = this;
    if (input.geometry && this.id === 'chat-input' && !options.preventScroll
        && this.selectionStart === this.value.length) {
      this.scrollTop = this.scrollHeight - this.clientHeight;
    }
  }
  /** Reveal relocated editor. */
  scrollIntoView() { this.inViewport = true; }
}

for (const match of input.html.matchAll(/<[a-z][a-z0-9]*\b([^>]*)>/gi)) {
  const attributes = Object.fromEntries(Array.from(
    match[1].matchAll(/([\w-]+)(?:="([^"]*)")?/g), (item) => [item[1], item[2] ?? ''],
  ));
  const id = attributes.id ?? 'anonymous-' + elements.size;
  const element = new Element(id);
  element.attributes = attributes;
  element.hidden = Object.hasOwn(attributes, 'hidden');
  elements.set(id, element);
}

const document = {
  activeElement: null,
  documentElement: {
    attributes: {lang: input.language},
    /** Read a document attribute. */
    getAttribute(name) { return this.attributes[name] ?? null; },
    /** Write a document attribute. */
    setAttribute(name, value) { this.attributes[name] = String(value); },
  },
  /** Read page element. */
  getElementById(id) { return elements.get(id) ?? null; },
  /** Create detached element. */
  createElement() { return new Element(); },
  /** Read translated elements. */
  querySelectorAll(selector) {
    const attribute = /^\[([\w-]+)\]$/.exec(selector);
    if (!attribute) throw new Error('Unsupported selector: ' + selector);
    return Array.from(elements.values())
      .filter((element) => Object.hasOwn(element.attributes, attribute[1]));
  },
};

const location = new URL('https://demo.example.test/');

/** Build one scripted response. */
function deliver(scripted) {
  if (scripted.error) throw new Error(scripted.error);
  if (scripted.status === 401) {
    return {
      ok: false,
      status: 401,
      json: async () => ({code: 'unauthorized', message: 'the token is wrong'}),
    };
  }
  if (scripted.status && scripted.status !== 200) {
    return {ok: false, status: scripted.status, json: async () => scripted.body};
  }
  return {ok: true, status: 200, json: async () => scripted.body};
}

const context = {
  document, location, URL, URLSearchParams, Headers,
  listeners: {},
  /** Register window events. */
  addEventListener(name, callback) { this.listeners[name] = callback; },
  /** Schedule native frame. */
  requestAnimationFrame(callback) { setTimeout(callback, 0); },
  console: Object.fromEntries(['log', 'error', 'warn', 'info', 'debug']
    .map((name) => [name, () => {}])),
  /** Serve scripted suggestions. */
  fetch: async (resource, options = {}) => {
    const headers = Object.fromEntries(new Headers(options.headers).entries());
    const target = new URL(String(resource), location);
    requests.push({
      url: target.href,
      method: options.method,
      headers,
      body: options.body,
    });
    const scripted = input.responses[nextResponse] ?? {body: null};
    nextResponse += 1;
    if (!scripted.hang) return deliver(scripted);
    return new Promise((resolve) => {
      setTimeout(() => resolve(deliver(scripted)), 0);
    });
  },
};
Object.defineProperty(context, 'localStorage', {
  get: () => {
    if (input.storageBlocked) throw new Error('Storage is blocked');
    return pageStorage;
  },
});
context.window = context;
vm.createContext(context);
vm.runInContext(input.script, context, {timeout: 1000});

/** Capture watched elements. */
function snapshot() {
  const watch = {};
  for (const id of input.watch) {
    const node = id.startsWith('i18n:')
      ? Array.from(elements.values()).find((element) =>
        element.attributes['data-i18n'] === id.slice('i18n:'.length))
      : elements.get(id);
    if (!node) {
      watch[id] = null;
      continue;
    }
    watch[id] = {
      value: node.value,
      accessibleName: node.attributes['aria-labelledby']
        ? node.attributes['aria-labelledby'].split(/\s+/)
          .map((id) => elements.get(id)?.textContent ?? '').join(' ')
        : node.attributes['aria-label'] ?? '',
      text: node.textContent,
      className: node.className,
      hidden: node.hidden,
      disabled: node.disabled,
      scrollTop: node.scrollTop,
      selectionStart: node.selectionStart,
      selectionEnd: node.selectionEnd,
      inViewport: node.inViewport,
      attributes: {...node.attributes},
    };
  }
  return watch;
}

/** Read rendered transcript. */
function transcript() {
  return Array.from(elements.get('messages').children).map((wrap) => ({
    className: wrap.className,
    author: wrap.children[0] ? wrap.children[0].textContent : '',
    text: wrap.children[1] ? wrap.children[1].textContent : '',
  }));
}

/** Read rendered inline text. */
function inlineText(node) {
  return node.children.map((child) =>
    typeof child === 'string' ? child : child.textContent).join('');
}

/** Read rendered check rows. */
function checkRows() {
  return Array.from(elements.get('checks').children).map((row) => ({
    name: row.children[0] ? row.children[0].textContent : '',
    status: row.children[1] ? row.children[1].textContent : '',
  }));
}

/** Read rendered usage rows. */
function usageRows() {
  return Array.from(elements.get('usage').children).map((row) => ({
    label: row.children[0] ? row.children[0].textContent : '',
    value: row.children[1] ? row.children[1].textContent : '',
  }));
}

/** Run one scripted step. */
async function runStep(step, entry) {
  const node = step.id === 'active' ? document.activeElement : elements.get(step.id);
  if (step.kind === 'set') {
    node.value = step.value;
    if (node.listeners.input) node.listeners.input();
  } else if (step.kind === 'select') {
    node.selectionStart = step.start;
    node.selectionEnd = step.end;
  } else if (step.kind === 'scroll') {
    node.scrollTop = step.top;
  } else if (step.kind === 'key') {
    if (document.activeElement !== node) node.focus();
    const event = {
      key: step.key,
      shiftKey: Boolean(step.shift),
      ctrlKey: Boolean(step.ctrl),
      metaKey: Boolean(step.meta),
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
    };
    if (node.listeners.keydown) node.listeners.keydown(event);
    if (event.key === 'Enter' && !event.defaultPrevented
        && node.attributes.type === 'button' && node.listeners.click) {
      node.listeners.click({target: node});
    }
    entry.defaultPrevented = event.defaultPrevented;
  } else if (step.kind === 'change') {
    node.value = step.value;
    if (node.listeners.change) node.listeners.change({target: node});
  } else if (step.kind === 'click') {
    if (node.disabled) {
      entry.refused = true;
    } else if (node.listeners.click) {
      node.focus();
      node.listeners.click({target: node});
    }
  } else if (step.kind === 'disclose') {
    node.open = Boolean(step.open);
    if (node.open) node.attributes.open = '';
    else delete node.attributes.open;
  } else if (step.kind === 'wait') {
    await new Promise((resolve) => setTimeout(resolve, 20));
  } else if (step.kind === 'resize') {
    Object.assign(input.geometry, step.geometry);
    const editor = elements.get('chat-input');
    editor.scrollTop = editor.scrollTop;
    if (context.listeners.resize) context.listeners.resize();
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

(async () => {
  const trace = [];
  for (const step of input.steps) {
    const entry = {step: step.kind, id: step.id ?? null};
    await runStep(step, entry);
    entry.watch = snapshot();
    entry.documentLang = document.documentElement.attributes.lang;
    trace.push(entry);
  }
  process.stdout.write(JSON.stringify({
    requests,
    trace,
    messages: transcript(),
    state: elements.get('assistant-state').textContent,
    reply: elements.get('reply').textContent,
    hint: inlineText(elements.get('hint')),
    checks: checkRows(),
    usage: usageRows(),
    storage: storageWrites,
    documentLang: document.documentElement.attributes.lang,
    focusLog,
    activeElement: document.activeElement ? document.activeElement.id : null,
  }));
})().catch((error) => { process.stderr.write(String(error)); process.exitCode = 1; });
"""

# === Execution ===


def run_editor_page(
    steps: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    *,
    language: str = 'en',
    watch: tuple[str, ...] = (),
    geometry: dict[str, int | bool] | None = None,
    storage: dict[str, str] | None = None,
    storage_blocked: bool = False,
) -> dict[str, Any]:
    """Observe editor page steps."""
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js is required for editor page tests')
    source = Path(__file__).parents[1] / 'src/reply_assistant/static/index.html'
    html = source.read_text(encoding='utf-8')
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
    payload = {
        'html': html,
        'script': '\n'.join(scripts),
        'language': language,
        'responses': list(responses),
        'steps': list(steps),
        'watch': list(watch),
        'geometry': geometry,
        'storage': dict(storage or {}),
        'storageBlocked': storage_blocked,
    }
    completed = subprocess.run(  # noqa: S603
        [node, '-e', RUNTIME],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    result: dict[str, Any] = json.loads(completed.stdout)
    return result
