"""Brief box under the txt2img positive prompt. Writes a caption and stores favorites."""

import json
import re
import sqlite3
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import gradio as gr
from gradio.context import get_render_context, set_render_context

from modules import scripts
from modules.ui_components import ToolButton

EXTENSION_DIR = Path(__file__).resolve().parents[1]
SKILL_PATH = EXTENSION_DIR / "skill" / "SKILL.md"
DB_PATH = EXTENSION_DIR / "data" / "favorites.sqlite"
OLLAMA = "http://127.0.0.1:11434"
CAPTION_RULE = 'This call is caption-only and must output exactly {"caption":"...","title":"..."}. The title is a few words.'
REFRESH_ICON = "\U0001f504"
DELETE_ICON = "\U0001f5d1\ufe0f"
PAGE_SIZE = 20


def log(message):
    if _log_enabled:
        print(f"[mossy-generate-neo] {message}", flush=True)


def log_exc(message):
    log(message)
    if _log_enabled:
        traceback.print_exc()


def set_log(enabled):
    global _log_enabled
    _log_enabled = bool(enabled)


_log_enabled = False

_spec = spec_from_file_location(
    "mossy_compile_prompt",
    EXTENSION_DIR / "skill" / "scripts" / "compile_prompt.py",
)
_compile = module_from_spec(_spec)
_spec.loader.exec_module(_compile)
compile_prompt = _compile.compile_prompt

SCHEMA = """
CREATE TABLE IF NOT EXISTS favorites (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS favorites_fts USING fts5(
    title,
    prompt,
    content='favorites',
    content_rowid='rowid'
);
CREATE TRIGGER IF NOT EXISTS favorites_ai AFTER INSERT ON favorites BEGIN
    INSERT INTO favorites_fts(rowid, title, prompt)
    VALUES (new.rowid, new.title, new.prompt);
END;
CREATE TRIGGER IF NOT EXISTS favorites_ad AFTER DELETE ON favorites BEGIN
    INSERT INTO favorites_fts(favorites_fts, rowid, title, prompt)
    VALUES ('delete', old.rowid, old.title, old.prompt);
END;
"""


def connect(path=None):
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def database(path=None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fts_match(text):
    # FTS5 prefix is a trailing star: "tea"* matches teapot, not a mid-word hit.
    words = re.findall(r"\w+", text or "", flags=re.UNICODE)
    return " ".join('"' + word.replace('"', '""') + '"*' for word in words)


def allocate_id(conn, moment):
    base = moment.strftime("%Y%m%d-%H%M%S")
    favorite_id = base
    suffix = 2
    while conn.execute("SELECT 1 FROM favorites WHERE id = ?", (favorite_id,)).fetchone():
        favorite_id = f"{base}-{suffix}"
        suffix += 1
    return favorite_id


def insert_favorite(title, prompt, path=None, moment=None):
    with database(path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        favorite_id = allocate_id(conn, moment or datetime.now())
        conn.execute(
            "INSERT INTO favorites (id, title, prompt) VALUES (?, ?, ?)",
            (favorite_id, title, prompt),
        )
        return favorite_id


def delete_favorite_row(favorite_id, path=None):
    with database(path) as conn:
        conn.execute("DELETE FROM favorites WHERE id = ?", (str(favorite_id),))


def search_favorites(query, path=None, page=0):
    page = max(0, int(page))
    offset = page * PAGE_SIZE
    with database(path) as conn:
        if not (query or "").strip():
            return conn.execute(
                "SELECT id, title, prompt FROM favorites ORDER BY id DESC LIMIT ? OFFSET ?",
                (PAGE_SIZE, offset),
            ).fetchall()
        match = fts_match(query)
        if not match:
            return []
        return conn.execute(
            """
            SELECT favorites.id, favorites.title, favorites.prompt
            FROM favorites_fts
            JOIN favorites ON favorites.rowid = favorites_fts.rowid
            WHERE favorites_fts MATCH ?
            ORDER BY favorites.id DESC
            LIMIT ? OFFSET ?
            """,
            (match, PAGE_SIZE, offset),
        ).fetchall()


def favorite_count(query, path=None):
    with database(path) as conn:
        if not (query or "").strip():
            return conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
        match = fts_match(query)
        if not match:
            return 0
        return conn.execute(
            "SELECT COUNT(*) FROM favorites_fts WHERE favorites_fts MATCH ?",
            (match,),
        ).fetchone()[0]


def page_span(total, page):
    if total <= 0:
        return 0, 0
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    return min(max(0, int(page)), pages - 1), pages


def favorite_prompt(favorite_id, path=None):
    if favorite_id is None or favorite_id == "":
        return None
    with database(path) as conn:
        row = conn.execute(
            "SELECT prompt FROM favorites WHERE id = ?",
            (str(favorite_id),),
        ).fetchone()
    return None if row is None else row[0]


def favorite_rows(query, path=None, page=0):
    rows = []
    for favorite_id, title, prompt in search_favorites(query, path, page):
        line = (prompt or "").strip().split("\n", 1)[0]
        rows.append((favorite_id, f"{title}\n{line}" if line else title))
    return rows


def empty_note(query, total):
    if total:
        return ""
    if (query or "").strip():
        return "No matches"
    return "No favorites"


def slot_values(query, page=0, path=None):
    total = favorite_count(query, path)
    page, pages = page_span(total, page)
    shown = favorite_rows(query, path, page) if total else []
    ids = [favorite_id for favorite_id, _label in shown]
    row_updates = []
    card_updates = []
    for index in range(PAGE_SIZE):
        if index < len(shown):
            row_updates.append(gr.update(visible=True))
            card_updates.append(gr.update(value=shown[index][1]))
        else:
            row_updates.append(gr.update(visible=False))
            card_updates.append(gr.update(value=""))
    note = empty_note(query, total)
    return (
        ids,
        page,
        gr.update(value="" if total == 0 else f"{page + 1} / {pages}", visible=total > 0),
        gr.update(interactive=page > 0),
        gr.update(interactive=pages > 0 and page < pages - 1),
        gr.update(value=note, visible=total == 0),
        *row_updates,
        *card_updates,
    )


def skipped_list():
    return (gr.skip(),) * (6 + PAGE_SIZE * 2)


def ollama_base(url):
    text = (url or "").strip().rstrip("/")
    return text or OLLAMA


def fetch_model_names(url=None):
    request = urllib.request.Request(ollama_base(url) + "/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [item["name"] for item in payload.get("models", []) if item.get("name")]


def model_state(url=None):
    base = ollama_base(url)
    try:
        names = fetch_model_names(base)
    except Exception as error:
        log_exc(f"models failed: {base}: {error}")
        return [], None, False, "Ollama is not running"
    log(f"models: {len(names)} from {base}")
    return names, (names[0] if names else None), True, ""


def error_update(text):
    text = text or ""
    return gr.update(value=text, visible=bool(text))


def load_models(url):
    names, value, interactive, error = model_state(url)
    return gr.update(choices=names, value=value, interactive=interactive), error_update(error)


def strip_think(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"<think>.*", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def parse_caption(text):
    text = strip_think(text).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("Model did not return a JSON object")
    try:
        draft, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as error:
        raise ValueError(f"Model did not return a JSON object: {error}") from error
    if not isinstance(draft, dict) or set(draft) != {"caption", "title"}:
        raise ValueError("Model JSON must contain only caption and title")
    title = draft["title"]
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Model JSON title must be nonempty text")
    return compile_prompt({"caption": draft["caption"]}), title.strip()


def ollama_chat(model, brief, temperature, keep_alive, url):
    base = ollama_base(url)
    skill = SKILL_PATH.read_text(encoding="utf-8").rstrip()
    payload = {
        "model": model,
        "think": False,
        "stream": False,
        "messages": [
            {"role": "system", "content": skill + "\n" + CAPTION_RULE},
            {"role": "user", "content": brief or ""},
        ],
        "options": {
            "temperature": float(temperature),
            "num_ctx": 8192,
            "num_predict": 2048,
        },
    }
    if not keep_alive:
        payload["keep_alive"] = 0
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base + "/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or str(error)) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Ollama is not running") from error
    if body.get("error"):
        raise RuntimeError(str(body["error"]))
    content = (body.get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty message")
    return content


def write_prompt(brief, model, keep_alive, temperature, url):
    if not model:
        log("write skipped: no model selected")
        return gr.skip(), gr.skip(), error_update("No model selected")
    base = ollama_base(url)
    log(f"write url={base} model={model} temperature={temperature} keep_alive={bool(keep_alive)} brief={brief!r}")
    try:
        raw = ollama_chat(model, brief, temperature, keep_alive, base)
        log("model output:\n" + raw)
        caption, title = parse_caption(raw)
    except Exception as error:
        log_exc(f"write failed: {error}")
        return gr.skip(), gr.skip(), error_update(str(error))
    log(f"write ok title={title!r}")
    return caption, title, error_update("")


def save_favorite(title, prompt, search):
    if not (prompt or "").strip():
        log("save skipped: positive prompt is empty")
        return (error_update("Positive prompt is empty"), *skipped_list())
    title = (title or "").strip() or (prompt or "").strip()[:60]
    try:
        favorite_id = insert_favorite(title, prompt)
    except Exception as error:
        log_exc(f"save failed: {error}")
        return (error_update(str(error)), *skipped_list())
    log(f"saved {favorite_id} title={title!r}")
    return (error_update(f"Saved {favorite_id}"), *slot_values(search, 0))


def apply_favorite(favorite_id):
    prompt = favorite_prompt(favorite_id)
    if prompt is None:
        log(f"favorite missing: {favorite_id}")
        return gr.skip(), gr.skip()
    log(f"use {favorite_id}")
    return prompt, error_update("")


def use_at(index, id_list):
    favorite_id = id_list[index] if id_list and index < len(id_list) else None
    if not favorite_id:
        log(f"favorite missing: slot {index}")
        return gr.skip(), gr.skip()
    return apply_favorite(favorite_id)


def delete_at(index, id_list, search, page):
    favorite_id = id_list[index] if id_list and index < len(id_list) else None
    if not favorite_id:
        log(f"favorite missing: slot {index}")
        return (gr.skip(), *skipped_list())
    try:
        delete_favorite_row(favorite_id)
    except Exception as error:
        log_exc(f"delete failed: {error}")
        return (error_update(str(error)), *skipped_list())
    log(f"deleted {favorite_id}")
    return (error_update("Deleted"), *slot_values(search, page))


def run_search(text):
    log(f"search {text!r}")
    try:
        return slot_values(text, 0)
    except Exception as error:
        log_exc(f"search failed: {text!r}: {error}")
        return skipped_list()


def clear_search():
    log("search cleared")
    try:
        return ("", *slot_values("", 0))
    except Exception as error:
        log_exc(f"search failed: '': {error}")
        return (gr.skip(), *skipped_list())


class Script(scripts.Script):
    def title(self):
        return "Mossy Generate"

    def show(self, is_img2img):
        return False if is_img2img else scripts.AlwaysVisible

    def ui(self, is_img2img):
        return None

    def after_component(self, component, **kwargs):
        if kwargs.get("elem_id") != "txt2img_prompt" or getattr(self, "_built", False):
            return
        row = getattr(component, "parent", None)
        holder = getattr(row, "parent", None)
        if holder is None:
            print("[mossy-generate-neo] txt2img prompt has no parent to stack under")
            return
        self._built = True
        # Prompt textbox lives in a horizontal row; stack the block on that row's parent.
        previous = get_render_context()
        set_render_context(holder)
        try:
            self._build(component)
        finally:
            set_render_context(previous)

    def _build(self, prompt_component):
        names, value, interactive, error = model_state()
        with gr.Column(elem_id="mossy_generate_neo"):
            with gr.Row(elem_classes=["mossy-brief-row"]):
                brief = gr.Textbox(label="Brief", lines=2, elem_id="mossy_brief")
                with gr.Column(elem_classes=["mossy-brief-actions"], scale=0, min_width=0):
                    write = gr.Button("Generate", elem_id="mossy_write")
                    save = gr.Button("Save", elem_id="mossy_save")
            with gr.Row(elem_classes=["mossy-actions"]):
                ollama_url = gr.Textbox(
                    label="Ollama",
                    value=OLLAMA,
                    elem_id="mossy_ollama",
                )
                model_dropdown = gr.Dropdown(
                    label="Model",
                    choices=names,
                    value=value,
                    interactive=interactive,
                    elem_id="mossy_model",
                )
                recheck = ToolButton(REFRESH_ICON, elem_id="mossy_recheck", tooltip="Recheck")
                with gr.Column(elem_classes=["mossy-checks"], scale=0, min_width=0):
                    keep_alive = gr.Checkbox(label="Keep alive", value=False, elem_id="mossy_keep_alive")
                    log_toggle = gr.Checkbox(label="Log", value=False, elem_id="mossy_log")
                temperature = gr.Slider(
                    label="Temperature",
                    minimum=0,
                    maximum=2,
                    step=0.1,
                    value=0.7,
                    elem_id="mossy_temperature",
                )
            title = gr.Textbox(visible=False, elem_id="mossy_title")
            error_box = gr.Textbox(
                value=error,
                lines=1,
                interactive=False,
                show_label=False,
                visible=bool(error),
                elem_id="mossy_error",
            )
            total = favorite_count("")
            page_index, pages = page_span(total, 0)
            shown = favorite_rows("", page=page_index) if total else []
            ids = gr.State([favorite_id for favorite_id, _label in shown])
            page_state = gr.State(page_index)
            with gr.Accordion("Favorites", open=False):
                with gr.Row(elem_classes=["mossy-search-row"]):
                    search = gr.Textbox(
                        show_label=False,
                        placeholder="Search",
                        elem_id="mossy_search",
                    )
                    find = gr.Button("Search", elem_id="mossy_find", elem_classes=["mossy-fit"])
                    clear = gr.Button("Clear", elem_id="mossy_clear", elem_classes=["mossy-fit"])
                with gr.Row(elem_classes=["mossy-page-row"]):
                    prev = gr.Button(
                        "Previous",
                        variant="secondary",
                        elem_classes=["mossy-fit"],
                        interactive=False,
                        elem_id="mossy_prev",
                    )
                    page_label = gr.Markdown(
                        "" if total == 0 else f"{page_index + 1} / {pages}",
                        visible=total > 0,
                        elem_classes=["mossy-page-label"],
                        elem_id="mossy_page_label",
                    )
                    next_page = gr.Button(
                        "Next",
                        variant="secondary",
                        elem_classes=["mossy-fit"],
                        interactive=pages > 1,
                        elem_id="mossy_next",
                    )
                empty = gr.Markdown(
                    empty_note("", total),
                    visible=total == 0,
                    elem_id="mossy_empty",
                )
                card_rows = []
                cards = []
                deletes = []
                with gr.Column(elem_classes=["mossy-card-list"]):
                    for index in range(PAGE_SIZE):
                        visible = index < len(shown)
                        with gr.Row(visible=visible, elem_classes=["mossy-card-row"]) as card_row:
                            cards.append(
                                gr.Button(
                                    shown[index][1] if visible else "",
                                    elem_classes=["mossy-card"],
                                )
                            )
                            deletes.append(ToolButton(DELETE_ICON, tooltip="Delete favorite"))
                        card_rows.append(card_row)

        list_outputs = [ids, page_state, page_label, prev, next_page, empty, *card_rows, *cards]
        log_toggle.change(set_log, inputs=[log_toggle])
        recheck.click(load_models, inputs=[ollama_url], outputs=[model_dropdown, error_box])
        write.click(
            lambda: gr.update(interactive=False),
            outputs=[write],
        ).then(
            write_prompt,
            inputs=[brief, model_dropdown, keep_alive, temperature, ollama_url],
            outputs=[prompt_component, title, error_box],
        ).then(
            lambda: gr.update(interactive=True),
            outputs=[write],
        )
        save.click(
            save_favorite,
            inputs=[title, prompt_component, search],
            outputs=[error_box, *list_outputs],
        )
        find.click(run_search, inputs=[search], outputs=list_outputs)
        search.submit(run_search, inputs=[search], outputs=list_outputs)
        clear.click(clear_search, outputs=[search, *list_outputs])
        prev.click(
            lambda query, current: slot_values(query, current - 1),
            inputs=[search, page_state],
            outputs=list_outputs,
        )
        next_page.click(
            lambda query, current: slot_values(query, current + 1),
            inputs=[search, page_state],
            outputs=list_outputs,
        )
        for index in range(PAGE_SIZE):
            cards[index].click(
                lambda id_list, index=index: use_at(index, id_list),
                inputs=[ids],
                outputs=[prompt_component, error_box],
            )
            deletes[index].click(
                lambda id_list, text, current, index=index: delete_at(index, id_list, text, current),
                inputs=[ids, search, page_state],
                outputs=[error_box, *list_outputs],
            )


def _self_check():
    assert compile_prompt({"caption": "A red teapot."}) == "A red teapot."
    caption, title = parse_caption('{"caption":"A red teapot.","title":" red teapot "}\nextra')
    assert caption == "A red teapot."
    assert title == "red teapot"
    assert fts_match('tea "pot') == '"tea"* "pot"*'
    assert ollama_base(" http://127.0.0.1:9/ ") == "http://127.0.0.1:9"
    assert ollama_base("  ") == OLLAMA
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "favorites.sqlite"
        moment = datetime(2026, 11, 23, 16, 30, 0)
        first = insert_favorite("red teapot", "A red teapot on a wooden table.", path, moment)
        second = insert_favorite("other", "A blue cup.", path, moment)
        assert first == "20261123-163000"
        assert second == "20261123-163000-2"
        assert [row[0] for row in search_favorites("", path)] == [second, first]
        assert [row[0] for row in favorite_rows("", path)] == [second, first]
        assert favorite_rows("wooden", path)[0][1].startswith("red teapot\nA red teapot")
        assert search_favorites("tea", path)[0][0] == first
        assert search_favorites("wooden", path)[0][0] == first
        assert search_favorites("***", path) == []
        assert favorite_prompt(first, path).startswith("A red teapot")
        delete_favorite_row(first, path)
        assert [row[0] for row in search_favorites("", path)] == [second]
        assert search_favorites("tea", path) == []
        assert search_favorites("wooden", path) == []
        assert favorite_prompt(first, path) is None
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "favorites.sqlite"
        moment = datetime(2026, 11, 23, 16, 0, 0)
        made = [
            insert_favorite(f"item {index}", f"prompt {index} tea", path, moment + timedelta(seconds=index))
            for index in range(PAGE_SIZE + 1)
        ]
        first_page = search_favorites("", path, 0)
        second_page = search_favorites("", path, 1)
        assert len(first_page) == PAGE_SIZE
        assert [row[0] for row in first_page] == list(reversed(made[1:]))
        assert [row[0] for row in second_page] == [made[0]]
        assert favorite_count("", path) == PAGE_SIZE + 1
        assert favorite_count("tea", path) == PAGE_SIZE + 1
        assert favorite_count("***", path) == 0
        assert search_favorites("tea", path, 1)[0][0] == made[0]
        assert empty_note("", 0) == "No favorites"
        assert empty_note("tea", 0) == "No matches"
        assert page_span(0, 3) == (0, 0)
        assert page_span(PAGE_SIZE + 1, 9) == (1, 2)
    print("mossy self-check ok")


if __name__ == "__main__":
    _self_check()
