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
const elements = new Map();
let nextResponse = 0;

/** Represent page elements. */
class Element {
  /** Initialize observed state. */
  constructor(id = '') {
    this.id = id;
    this.children = [];
    this.value = '';
    this.textContent = '';
    this.className = '';
    this.hidden = false;
    this.disabled = false;
    this.scrollTop = undefined;
    this.selectionStart = undefined;
    this.selectionEnd = undefined;
    this.attributes = {};
    this.listeners = {};
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
  focus() { focusLog.push(this.id); }
}

for (const match of input.html.matchAll(/<[a-z][a-z0-9]*\b([^>]*)>/gi)) {
  const attributes = Object.fromEntries(Array.from(
    match[1].matchAll(/([\w-]+)="([^"]*)"/g), (item) => [item[1], item[2]],
  ));
  const id = attributes.id ?? 'anonymous-' + elements.size;
  const element = new Element(id);
  element.attributes = attributes;
  elements.set(id, element);
}

const document = {
  documentElement: {getAttribute: () => input.language},
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
  return {ok: true, status: 200, json: async () => scripted.body};
}

const context = {
  document, location, URL, URLSearchParams, Headers,
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
context.window = context;
vm.createContext(context);
vm.runInContext(input.script, context, {timeout: 1000});

/** Capture watched elements. */
function snapshot() {
  const watch = {};
  for (const id of input.watch) {
    const node = elements.get(id);
    if (!node) {
      watch[id] = null;
      continue;
    }
    watch[id] = {
      value: node.value,
      text: node.textContent,
      className: node.className,
      hidden: node.hidden,
      disabled: node.disabled,
      scrollTop: node.scrollTop,
      selectionStart: node.selectionStart,
      selectionEnd: node.selectionEnd,
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

/** Run one scripted step. */
async function runStep(step, entry) {
  const node = elements.get(step.id);
  if (step.kind === 'set') {
    node.value = step.value;
    if (node.listeners.input) node.listeners.input();
  } else if (step.kind === 'select') {
    node.selectionStart = step.start;
    node.selectionEnd = step.end;
  } else if (step.kind === 'scroll') {
    node.scrollTop = step.top;
  } else if (step.kind === 'key') {
    const event = {
      key: step.key,
      shiftKey: Boolean(step.shift),
      ctrlKey: Boolean(step.ctrl),
      metaKey: Boolean(step.meta),
      defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
    };
    if (node.listeners.keydown) node.listeners.keydown(event);
    entry.defaultPrevented = event.defaultPrevented;
  } else if (step.kind === 'click') {
    if (node.disabled) {
      entry.refused = true;
    } else if (node.listeners.click) {
      node.listeners.click({target: node});
    }
  } else if (step.kind === 'wait') {
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

(async () => {
  const trace = [];
  for (const step of input.steps) {
    const entry = {step: step.kind, id: step.id ?? null};
    await runStep(step, entry);
    entry.watch = snapshot();
    trace.push(entry);
  }
  process.stdout.write(JSON.stringify({
    requests,
    trace,
    messages: transcript(),
    state: elements.get('assistant-state').textContent,
    reply: elements.get('reply').textContent,
    focusLog,
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
