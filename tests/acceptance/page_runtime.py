"""Execute page request behavior."""

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
const logs = [];
const storage = [];
const cookies = [];
const elements = new Map();

/** Represent page elements. */
class Element {
  /** Initialize visible state. */
  constructor(id = '') {
    this.id = id;
    this.children = [];
    this.value = '';
    this.textContent = '';
    this.className = '';
    this.hidden = false;
    this.disabled = false;
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
  /** Focus input element. */
  focus() {}
}

for (const match of input.html.matchAll(/\bid="([^"]+)"/g)) {
  elements.set(match[1], new Element(match[1]));
}
const document = {
  documentElement: {getAttribute: () => input.language},
  /** Read page element. */
  getElementById(id) { return elements.get(id) ?? null; },
  /** Create detached element. */
  createElement() { return new Element(); },
  /** Read translated elements. */
  querySelectorAll() { return []; },
};
Object.defineProperty(document, 'cookie', {
  get: () => '',
  set: (value) => cookies.push(String(value)),
});

/** Build recording storage. */
function recordedStorage(name) {
  return {
    getItem: () => null,
    setItem: (key, value) => storage.push([name, String(key), String(value)]),
    removeItem: () => {},
  };
}

const location = new URL('https://demo.example.test/' + input.suffix);
const context = {
  document, location, URL, URLSearchParams, Headers,
  localStorage: recordedStorage('local'),
  sessionStorage: recordedStorage('session'),
  console: Object.fromEntries(['log', 'error', 'warn', 'info', 'debug']
    .map((name) => [name, (...values) => logs.push(values.map(String).join(' '))])),
  history: {replaceState: () => { throw new Error('Token link must survive reload'); }},
  /** Record suggestion request. */
  fetch: async (resource, options = {}) => {
    const headers = Object.fromEntries(new Headers(options.headers).entries());
    const target = new URL(String(resource), location);
    const request = {
      url: target.href,
      method: options.method,
      headers,
      body: options.body,
    };
    requests.push(request);
    if (input.failure_message !== null) throw new Error(input.failure_message);
    const accepted = input.expected_token === null
      || headers['x-api-token'] === input.expected_token;
    return {
      ok: accepted,
      status: accepted ? 200 : 401,
      json: async () => accepted ? {
        customer_reply: 'Scripted customer reply.',
        upsell_product_id: null,
        upsell_hint: 'Scripted manager hint.',
        kb_match: 'found',
        checks: {rejected: [], disclaimer_appended: false},
        usage: {input_tokens: 1, output_tokens: 1, provider: 'fake', attempts: 1},
      } : {code: 'unauthorized', message: 'the API token is missing or wrong'},
    };
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(input.script, context, {timeout: 1000});

/** Read rendered element. */
function rendered(node) {
  if (typeof node === 'string') return node;
  return String(node.textContent) + node.children.map(rendered).join('');
}

(async () => {
  for (const message of input.messages) {
    document.getElementById('customer-input').value = message;
    const button = document.getElementById('add-customer');
    if (!button.disabled) button.listeners.click({target: button});
    await new Promise(setImmediate);
  }
  process.stdout.write(JSON.stringify({
    requests, logs, storage, cookies,
    state: document.getElementById('assistant-state').textContent,
    reply: document.getElementById('reply').textContent,
    visible: Array.from(elements.values()).map(rendered).join(''),
  }));
})().catch((error) => { process.stderr.write(String(error)); process.exitCode = 1; });
"""

# === Execution ===


def run_page(
    suffix: str,
    expected_token: str | None,
    *,
    language: str = 'en',
    messages: tuple[str, ...] = ('First question',),
    failure_message: str | None = None,
) -> dict[str, Any]:
    """Observe actual page requests."""
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js is required for page acceptance tests')
    source = Path(__file__).parents[2] / 'src/reply_assistant/static/index.html'
    html = source.read_text(encoding='utf-8')
    scripts = re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
    payload = {
        'html': html,
        'script': '\n'.join(scripts),
        'suffix': suffix,
        'language': language,
        'expected_token': expected_token,
        'messages': messages,
        'failure_message': failure_message,
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
