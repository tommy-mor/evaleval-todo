"""
Todo list app — strophe demo.

    uv run uvicorn app:app --reload
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from poem import (
    Signer, exec_event, shell_html,
    apply_snippet_substitutions,
    One, Three,
    Selector, Eval, MORPH,
)

app = FastAPI()
signer = Signer()

# --- State (in-memory, list of dicts) ---

TODOS: list[dict] = []


def _find(todo_id: str) -> dict | None:
    return next((t for t in TODOS if t["id"] == todo_id), None)


# --- Hiccup components ---

def snippet_hidden(code: str) -> list:
    return signer.snippet_hidden(code)


def todo_item(t: dict) -> list:
    done_class = "done" if t["done"] else ""
    return ["li", {"id": f"todo-{t['id']}", "class": f"todo-item {done_class}".strip()},
        ["form.inline", {"action": "/do", "method": "post", "data-reset": "false"},
            *snippet_hidden(f"toggle('{t['id']}')"),
            ["button.toggle", {"type": "submit"}, "x" if t["done"] else "o"],
        ],
        ["span.text", t["text"]],
        ["form.inline", {"action": "/do", "method": "post"},
            *snippet_hidden(f"delete('{t['id']}')"),
            ["button.delete", {"type": "submit"}, "del"],
        ],
    ]


def todo_list() -> list:
    items = [todo_item(t) for t in TODOS]
    return ["ul#todo-list", items]


def add_form() -> list:
    return ["form#add-form", {"action": "/do", "method": "post"},
        *snippet_hidden("add($text)"),
        ["input", {"type": "text", "name": "text", "placeholder": "what needs doing?", "autofocus": "true"}],
        ["button", {"type": "submit"}, "add"],
    ]


def page() -> list:
    count = len([t for t in TODOS if not t["done"]])
    return ["div#app",
        ["h1", "todos"],
        add_form(),
        todo_list(),
        ["p.count", f"{count} remaining"],
    ]


STYLE = """
body { font-family: monospace; max-width: 600px; margin: 2em auto; padding: 0 1em; }
h1 { font-size: 1.5em; }
ul { list-style: none; padding: 0; }
.todo-item { display: flex; align-items: center; gap: 0.5em; padding: 0.3em 0; }
.todo-item.done .text { text-decoration: line-through; opacity: 0.5; }
.inline { display: inline; }
.toggle, .delete { cursor: pointer; background: none; border: 1px solid #ccc; padding: 0.1em 0.4em; font-family: monospace; }
.delete { color: #c33; }
input[type="text"] { font-family: monospace; padding: 0.3em; width: 300px; }
button[type="submit"] { font-family: monospace; padding: 0.3em 0.8em; cursor: pointer; }
.count { color: #666; font-size: 0.9em; }
"""


# --- Snippet sandbox functions ---

def add(text: str):
    text = text.strip()
    if not text:
        return PlainTextResponse("", status_code=204)
    TODOS.append({"id": uuid.uuid4().hex[:8], "text": text, "done": False})
    return PlainTextResponse(
        Three[Selector("#app")][MORPH][page()],
        status_code=200,
    )


def toggle(todo_id: str):
    t = _find(todo_id)
    if not t:
        return PlainTextResponse("not found", status_code=404)
    t["done"] = not t["done"]
    return PlainTextResponse(
        Three[Selector("#app")][MORPH][page()],
        status_code=200,
    )


def delete(todo_id: str):
    t = _find(todo_id)
    if not t:
        return PlainTextResponse("not found", status_code=404)
    TODOS.remove(t)
    return PlainTextResponse(
        Three[Selector("#app")][MORPH][page()],
        status_code=200,
    )


SANDBOX = {
    "add": add,
    "toggle": toggle,
    "delete": delete,
}


# --- Routes ---

@app.get("/sse")
async def sse(request: Request):
    from starlette.responses import StreamingResponse

    async def generate():
        yield exec_event(
            One[Eval(f"document.title = 'todos'")]
        )
        yield exec_event(
            f"document.head.insertAdjacentHTML('beforeend', `<style>{STYLE}</style>`)"
        )
        yield exec_event(
            Three[Selector("body")][MORPH][["body", page()]]
        )

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
async def index():
    return HTMLResponse(shell_html())


@app.post("/do")
async def do(request: Request):
    form = await request.form()

    snippet = form.get("__snippet__", "")
    sig = form.get("__sig__", "")
    nonce = form.get("__nonce__", "")

    if not all([snippet, sig, nonce]):
        return PlainTextResponse("Missing fields", status_code=400)
    if not signer.verify(snippet, nonce, sig):
        return PlainTextResponse("Invalid signature", status_code=403)
    if not signer.consume_nonce(nonce):
        return PlainTextResponse("Invalid nonce", status_code=403)

    form_data = {k: str(v) for k, v in form.items() if not k.startswith("__")}
    snippet = apply_snippet_substitutions(snippet, form_data)

    try:
        return eval(snippet, {"__builtins__": {}}, SANDBOX)
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)
