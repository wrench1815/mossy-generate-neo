# Mossy Generate

A box under the txt2img positive prompt in [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo). It sends a short brief to a local [Ollama](https://ollama.com) model, takes the caption that comes back, and replaces the positive prompt with it. It can also save that prompt and paste a saved one back later.

The extension does not generate the image. After the caption is in the prompt, use Forge's own Generate button.

It is txt2img only. img2img is unchanged.

## Requirements

- Forge Neo.
- Ollama running where Forge can reach it. The default address is `http://127.0.0.1:11434`.
- At least one model already pulled in Ollama. This extension does not download models.

No extra Python packages and no `install.py`. Gradio and the standard library are enough.

## Install

Clone this repository into the WebUI `extensions` directory so the path is `extensions/mossy-generate-neo`. From Forge, **Extensions → Install from URL** does the same thing once this repository has a git URL.

Restart the WebUI, or use Reload UI. The folder name is the name on the Extensions tab. Disable it there and reload to turn the box off.

Nothing is created at install time. The first time txt2img builds the box, the extension creates `data/` and `data/favorites.sqlite` inside its own folder, then creates the favorites tables if they are missing. An existing database is left as it is. That folder is not in the git repository. Updating or reinstalling the extension does not ship your favorites, and deleting the extension folder deletes them.

## What the box contains

Under the positive prompt:

- **Brief** — the short request sent to the model.
- **Generate** — ask Ollama for a caption and write it into the positive prompt.
- **Save** — store the current positive prompt as a favorite.
- **Ollama** — base URL. A trailing slash is ignored. An empty field uses `http://127.0.0.1:11434`.
- **Model** — models reported by that Ollama server. The first one is selected. The dropdown stays disabled when the server cannot be reached.
- **Recheck** — ask Ollama for the model list again. Use it after changing the URL or pulling a model.
- **Keep alive** — off by default. Off tells Ollama to unload the model when the request finishes. On leaves Ollama's normal keep-alive behavior.
- **Log** — on by default. On prints `[mossy-generate-neo]` lines to the Forge console, including the brief, the raw model output, and errors. Off silences those lines.
- **Temperature** — sent to Ollama with the request. Range 0 to 2, step 0.1, default 0.7.
- An error line under those controls. It shows while something failed and hides after the next successful action.
- **Favorites** — a closed accordion with search and up to 20 saved prompts.

## Generate

1. Start Ollama and confirm a model is listed. If the server is down at page load, the error line says `Ollama is not running`. Start it and press Recheck.
2. Write a brief. The model is instructed to expand it into one MOSS-Image caption and a short title, and to return only `{"caption":"...","title":"..."}`.
3. Press **Generate**.

On success the caption replaces the whole positive prompt. The title is kept hidden and is used only when you save. The brief is not written into the prompt and is not saved.

Each request uses an 8192-token context and allows up to 2048 tokens back. The call waits up to five minutes. Thinking tags and a surrounding ` ```json ` fence are stripped before the JSON is read. The model must return an object whose only fields are `caption` and `title`. Anything else, including a layout, is rejected and the positive prompt is left unchanged.

The error line also shows `No model selected` when Generate is pressed with an empty model dropdown, `Ollama returned an empty message` when the reply has no text, and the Ollama error text when the server rejects the request.

## Favorites

**Save** stores the current positive prompt, including edits you made after Generate. It does not store the brief. The hidden title from the last successful Generate is the name. If there is no title, the name is the first 60 characters of the prompt. Saving an empty prompt shows `Positive prompt is empty` and writes nothing.

Each favorite gets an id of the form `YYYYMMDD-HHMMSS`. A second save in the same second becomes `YYYYMMDD-HHMMSS-2`, then `-3`, and so on. The error line reports `Saved` plus that id.

Open **Favorites** to see the newest 20. Each row shows the title, the first line of the prompt, and a delete button.

- Press the row to replace the positive prompt with the full saved prompt.
- Press delete to remove that favorite. The row disappears and the error line says `Deleted`.
- **Search** matches words in the title and the prompt. Each word matches from the start of a word, so `tea` matches `teapot`. Several words must all match. Press the button or Enter. A search made only of punctuation shows no rows.
- **Clear** empties the search box and shows the newest 20 again.

Only 20 rows are shown. Older matches stay in the database and can show up in a later search. The database file is `extensions/mossy-generate-neo/data/favorites.sqlite`.

## License

Copyright (C) 2026 wrench1815. Licensed under the GNU Affero General Public License, version 3. See [LICENSE](LICENSE).
