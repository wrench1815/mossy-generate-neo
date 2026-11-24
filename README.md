# Mossy Generate

A box under the txt2img positive prompt in [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo). It sends a short brief to a local [Ollama](https://ollama.com) model, takes the caption that comes back, and replaces the positive prompt with it. It can also save that prompt and paste a saved one back later.

The extension does not generate the image. After the caption is in the prompt, use Forge's own Generate button.

It is txt2img only. img2img is unchanged.

## Requirements

- Forge Neo.
- Ollama running where Forge can reach it. The default address is `http://127.0.0.1:11434`.
- At least one model already pulled in Ollama. This extension does not download models.

Pull a local instruct model. Gemma writes the prose. Qwen holds the caption JSON more tightly. The abliterated tags are the same bases with the refusal filter removed, so they take an adult brief that the stock model refuses. That surgery also makes the JSON a bit less reliable. A smaller model often fails it outright. The error line shows that failure.

| Brief | Pull | About |
| --- | --- | --- |
| Adult | `huihui_ai/gemma-4-abliterated:12b` | Abliterated Gemma 4. Best prose of this set. About 7.6 GB. |
| Adult, and the 12B misses the JSON | `huihui_ai/qwen3-abliterated:14b` | Abliterated Qwen3. Stricter format, flatter prose. About 9 GB. |
| Ordinary | `gemma4:12b` | Stock Gemma 4. Same prose, refusals left on. |
| Ordinary, and Gemma misses the JSON | `qwen3:14b` | Stock Qwen3. |
| Ordinary, if it fits | `gpt-oss:20b` | Stock. About 14 GB. |

`huihui_ai/gemma-4-abliterated:31b` is the step up from the 12B when you have about 24 GB free. The Model menu lists whatever that Ollama server already has.

No extra Python packages and no `install.py`. Gradio and the standard library are enough.

## Install

Clone this repository into the WebUI `extensions` directory so the path is `extensions/mossy-generate-neo`. From Forge, **Extensions → Install from URL** does the same thing once this repository has a git URL.

Restart the WebUI, or use Reload UI. The folder name is the name on the Extensions tab. Disable it there and reload to turn the box off.

Nothing is created at install time. The first time txt2img builds the box, the extension creates `data/` and `data/favorites.sqlite` inside its own folder, then creates the favorites tables if they are missing. An existing database is left as it is. That folder is not in the git repository. Updating or reinstalling the extension does not ship your favorites, and deleting the extension folder deletes them.

## What the box contains

Under the positive prompt:

- **Brief** — the short request sent to the model. With [TagComplete Neo](https://github.com/eduardoabreu81/sd-webui-tagcomplete-neo) enabled, this box gets the same tag, embedding, and LoRA suggestions as the positive prompt. That uses TagComplete's **Active in third party textboxes** option, which is on by default. Without TagComplete, the box is plain text.
- **Generate** — ask Ollama for a caption and write it into the positive prompt.
- **Save** — store the current positive prompt as a favorite.
- **Ollama** — base URL. A trailing slash is ignored. An empty field uses `http://127.0.0.1:11434`.
- **Model** — models reported by that Ollama server. The first one is selected. The dropdown stays disabled when the server cannot be reached.
- **Recheck** — ask Ollama for the model list again. Use it after changing the URL or pulling a model.
- **Keep alive** — off by default. Off tells Ollama to unload the model when the request finishes. On leaves Ollama's normal keep-alive behavior.
- **Log** — off by default. On prints `[mossy-generate-neo]` lines to the Forge console, including the brief, the raw model output, and errors. Off silences those lines.
- **Temperature** — sent to Ollama with the request. Range 0 to 2, step 0.1, default 0.7.
- An error line under those controls. It shows while something failed and hides after the next successful action.
- **Favorites** — a closed accordion with search, 20 prompts per page, and previous/next.

## Generate

1. Start Ollama and confirm a model is listed. If the server is down at page load, the error line says `Ollama is not running`. Start it and press Recheck.
2. Write a brief. Every model is told to expand it into one caption in this order: subject and action, appearance, setting, camera and framing, medium, lighting, materials, palette, mood. A short or tag-like brief still has to fill that sequence. The reply must be only `{"caption":"...","title":"..."}`.
3. Press **Generate**. The button stays disabled until the request finishes, including when it fails.

On success the caption replaces the whole positive prompt. The title is kept hidden and is used only when you save. The brief is not written into the prompt and is not saved.

Each request uses an 8192-token context and allows up to 2048 tokens back. The call waits up to five minutes. Thinking tags and a surrounding ` ```json ` fence are stripped before the JSON is read. The model must return an object whose only fields are `caption` and `title`. Anything else, including a layout, is rejected and the positive prompt is left unchanged.

The error line also shows `No model selected` when Generate is pressed with an empty model dropdown, `Ollama returned an empty message` when the reply has no text, and the Ollama error text when the server rejects the request.

## Favorites

**Save** stores the current positive prompt, including edits you made after Generate. It does not store the brief. The hidden title from the last successful Generate is the name. If there is no title, the name is the first 60 characters of the prompt. Saving an empty prompt shows `Positive prompt is empty` and writes nothing.

Each favorite gets an id of the form `YYYYMMDD-HHMMSS`. A second save in the same second becomes `YYYYMMDD-HHMMSS-2`, then `-3`, and so on. The error line reports `Saved` plus that id.

Open **Favorites** to see the newest saved prompts, 20 per page. **Previous** and **Next** move between pages. The card list has a fixed height and scrolls inside it. Each row shows the title, the first line of the prompt, and a delete button. An empty list says `No favorites`.

- Press the row to replace the positive prompt with the full saved prompt.
- Press delete to remove that favorite. The row disappears and the error line says `Deleted`. The page stays put, and steps back when that page no longer has rows.
- **Search** matches words in the title and the prompt. Each word matches from the start of a word, so `tea` matches `teapot`. Several words must all match. Press the button or Enter. A search with no hits says `No matches`. A search made only of punctuation does the same.
- **Clear** empties the search box and shows the newest page again.
- **Save** and **Search** open the first page.

The database file is `extensions/mossy-generate-neo/data/favorites.sqlite`.

## License

Mossy Generate turns a short brief into a MOSS-Image caption and stores favorite prompts.
Copyright (C) 2026 wrench1815

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along with this program. If not, see <https://www.gnu.org/licenses/>. The full text is in [LICENSE](LICENSE).
