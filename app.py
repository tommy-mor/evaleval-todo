"""
Todo list app — strophe demo.

    uv run uvicorn app:app --reload
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from starlette.responses import StreamingResponse

from strophe import (
    Signer, SnippetExecutionError, exec_event, shell_html,
    One, Two, Three,
    Selector, Eval, MORPH, APPEND, REMOVE,
)

app = FastAPI()
signer = Signer()

# --- State (in-memory, list of dicts) ---

TODOS: list[dict] = []


def _find(todo_id: str) -> dict | None:
    return next((t for t in TODOS if t["id"] == todo_id), None)


# --- Hiccup components ---


def todo_item(t: dict) -> list:
    done_class = "done" if t["done"] else ""
    return ["li", {"id": f"todo-{t['id']}", "class": f"todo-item {done_class}".strip()},
        ["form.inline", {"action": "/do", "method": "post", "data-reset": "false"},
            *signer.snippet_hidden(f"toggle('{t['id']}')"),
            ["button.toggle", {"type": "submit"}, "x" if t["done"] else "o"],
        ],
        ["span.text", t["text"]],
        ["form.inline", {"action": "/do", "method": "post"},
            *signer.snippet_hidden(f"delete('{t['id']}')"),
            ["button.delete", {"type": "submit"}, "del"],
        ],
    ]


def todo_list() -> list:
    items = [todo_item(t) for t in TODOS]
    return ["ul#todo-list", items]


def add_form() -> list:
    return ["form#add-form", {"action": "/do", "method": "post"},
        *signer.snippet_hidden("add($text)"),
        ["input", {"type": "text", "name": "text", "placeholder": "what needs doing?", "autofocus": "true"}],
        ["button", {"type": "submit"}, "add"],
    ]


def remaining_count() -> list:
    count = len([t for t in TODOS if not t["done"]])
    return ["p.count", f"{count} remaining"]


def page() -> list:
    return ["div#app",
        ["h1", "todos"],
        add_form(),
        todo_list(),
        remaining_count(),
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
    t = {"id": uuid.uuid4().hex[:8], "text": text, "done": False}
    TODOS.append(t)
    return PlainTextResponse(
        ";".join([
            Three[Selector("#todo-list")][APPEND][todo_item(t)],
            Three[Selector("p.count")][MORPH][remaining_count()],
        ]),
        status_code=200,
    )


def toggle(todo_id: str):
    t = _find(todo_id)
    if not t:
        return PlainTextResponse("not found", status_code=404)
    t["done"] = not t["done"]
    return PlainTextResponse(
        ";".join([
            Three[Selector(f"#todo-{todo_id}")][MORPH][todo_item(t)],
            Three[Selector("p.count")][MORPH][remaining_count()],
        ]),
        status_code=200,
    )


def delete(todo_id: str):
    t = _find(todo_id)
    if not t:
        return PlainTextResponse("not found", status_code=404)
    TODOS.remove(t)
    return PlainTextResponse(
        ";".join([
            Two[Selector(f"#todo-{todo_id}")][REMOVE],
            Three[Selector("p.count")][MORPH][remaining_count()],
        ]),
        status_code=200,
    )


# --- Routes ---

@app.get("/sse")
async def sse(request: Request):

    async def generate():
        yield exec_event(
            One[Eval(f"document.title = 'todos'")]
        )
        yield exec_event(
            Three[Selector("head")][APPEND][["style", STYLE]]
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
    try:
        return signer.execute_signed_form(
            form=form,
            bindings={
                "add": add,
                "toggle": toggle,
                "delete": delete,
            },
        )
    except SnippetExecutionError as e:
        return PlainTextResponse(e.message, status_code=e.status_code)
