import json
import re
from typing import List, Dict

import anthropic

from . import config

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to your .env file before generating content."
        )
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def _extract_json(text: str):
    """Claude sometimes wraps JSON in prose or code fences; pull the JSON block out."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start_candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if start_candidates:
        start = min(start_candidates)
        text = text[start:]
    last_curly = text.rfind("}")
    last_square = text.rfind("]")
    end = max(last_curly, last_square)
    if end != -1:
        text = text[: end + 1]
    return json.loads(text)


SCRIPT_SYSTEM_PROMPT = """You are a professional YouTube narration scriptwriter. \
Write pure narration scripts following these rules exactly:

- Length: 1,800-2,500 words.
- Pure narration only - no headers, no bullet points, no visual cues, no stage \
directions, no parenthetical notes of any kind.
- Voice: calm, intelligent, second-person throughout ("you").
- Rhythm: short sentence. Short sentence. One longer sentence that adds depth. \
Short sentence. Ask a question every 4-6 sentences.
- Weave in at least 3 real named researchers or real studies naturally into the \
narration, if relevant to the topic.
- Open with a hook that makes the first 4 lines impossible to stop reading.
- End with a closing line that directly echoes the first line of the script, \
completely reframed.

Respond with ONLY a single JSON object, no commentary, no markdown fences, in \
exactly this shape:
{"title": "Full video title as a compelling headline", "script": "The full \
narration script as plain text, no markdown, no asterisks, no brackets, no \
stage directions, no title heading inside the text."}
"""


def generate_script(topic: str) -> Dict[str, str]:
    client = _get_client()
    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=8000,
        system=SCRIPT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Video topic: {topic}"}],
    )
    raw = "".join(block.text for block in message.content if block.type == "text")
    data = _extract_json(raw)
    return {"title": data["title"].strip(), "script": data["script"].strip()}


IMAGE_PROMPT_SYSTEM_PROMPT = """You are a visual director for a hand-drawn doodle-style \
educational YouTube explainer channel. You will be given a timestamped narration \
transcript, one line per timestamp. For every single timestamp line, produce ONE \
concrete scene description to be turned into a text-to-image prompt.

Rules for each scene description:
- Be specific: describe exactly what characters are present, what they are doing, \
their exact facial expression, what objects are in the scene, what background color \
is used, and whether any on-screen text or labels appear.
- Translate abstract narration into concrete visuals. Example: if the line says \
"your body doesn't know the difference", show a confused stick figure looking at two \
identical objects. If the line says "millions of years", show a large hourglass with \
bold ALL CAPS text "MILLIONS OF YEARS" at the top of the frame.
- Match tone to background color choice (e.g. warm/cozy = soft yellow or cream, \
tense/scary = deep blue or grey, exciting = bright orange, calm = pale green or blue).
- Hold the same scene across consecutive timestamps that describe the same moment - \
only change the character's expression or add one new element rather than inventing \
a brand new scene every few seconds. Say explicitly if a scene is a continuation of \
the previous one and describe only what changed.
- Where appropriate use one of these proven frame types: a concept text frame \
(large central object like an hourglass/clock/skull plus bold ALL CAPS text at top), \
a labeled diagram (object plus a yellow diagonal arrow plus an ALL CAPS label word), \
a figure reaction (thought bubble above the head containing '?', 'HMMMM', '!', or \
'WAIT...'), or a villain personified (an abstract concept given an angry cartoon face, \
e.g. a sun with a knife, a brain with boxing gloves).
- Critical JSON formatting rule: never use a double-quote character (") anywhere \
inside a "scene" value, including for on-screen text, labels, or thought-bubble \
words. Use single quotes (e.g. 'WAIT...') instead, since a raw double-quote inside \
the string breaks JSON parsing.

Respond with ONLY a single JSON array, no commentary, no markdown fences, in exactly \
this shape:
[{"timestamp": "00:00", "scene": "full scene description text"}, ...]
One array entry per input timestamp line, in the same order, covering every timestamp \
with no omissions.
"""

STYLE_ANCHOR = (
    "A hand-drawn, 2-D color watercolor style stick figure doodle illustration. "
    "Use simple brush-pen outlines with slightly wobbly, imperfect strokes. Reduce "
    "all details to cute, childlike shapes while preserving the main subject and "
    "composition. Naive sketchbook aesthetic, playful and whimsical character "
    "design, clean white background, minimal linework, expressive simplicity, "
    "handmade doodle style, water color ink drawing, charming imperfections, "
    "simple cartoon illustration. Do not mention the timestamp on the image."
)

STYLE_LOCK = (
    "no gradients, no shadows, no textures, no photorealism, no 3D, 16:9 aspect "
    "ratio, educational YouTube explainer doodle style."
)


def format_image_prompt(timestamp: str, scene: str) -> str:
    return f"[{timestamp}] {STYLE_ANCHOR} {scene}, {STYLE_LOCK}"


# Long scripts can produce 100-250+ timestamp lines. Asking Claude for every scene
# in one response risks the reply being cut off mid-JSON when it hits max_tokens
# (observed: 8000 output tokens truncates around ~130 entries), which breaks JSON
# parsing entirely. Chunking keeps each call comfortably within budget regardless
# of script length, at the cost of one extra call per ~35 lines.
IMAGE_PROMPT_CHUNK_SIZE = 35
IMAGE_PROMPT_MAX_TOKENS = 6000


def generate_image_prompts(timestamped_lines: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """timestamped_lines: [{"timestamp": "00:00", "text": "..."}, ...]
    Returns [{"timestamp": "00:00", "scene": "...", "prompt": "full formatted prompt"}, ...]
    """
    client = _get_client()
    all_scenes: List[Dict[str, str]] = []
    previous_scene: str | None = None

    for start in range(0, len(timestamped_lines), IMAGE_PROMPT_CHUNK_SIZE):
        chunk = timestamped_lines[start : start + IMAGE_PROMPT_CHUNK_SIZE]
        transcript_block = "\n".join(f"[{ln['timestamp']}] {ln['text']}" for ln in chunk)
        if previous_scene:
            user_content = (
                "For continuity, the scene immediately before this excerpt was:\n"
                f"{previous_scene}\n\n"
                "Continue naturally from there (per the hold-scene rule) for the "
                f"following timestamps:\n{transcript_block}"
            )
        else:
            user_content = transcript_block

        message = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=IMAGE_PROMPT_MAX_TOKENS,
            system=IMAGE_PROMPT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = "".join(block.text for block in message.content if block.type == "text")
        if message.stop_reason == "max_tokens":
            raise RuntimeError(
                "Claude's response was cut off before finishing this chunk of image "
                "prompts. Try lowering IMAGE_PROMPT_CHUNK_SIZE in app/llm.py."
            )
        scenes = _extract_json(raw)
        all_scenes.extend(scenes)
        if scenes:
            previous_scene = scenes[-1]["scene"]

    scene_by_ts = {s["timestamp"]: s["scene"] for s in all_scenes}
    results = []
    for line in timestamped_lines:
        ts = line["timestamp"]
        scene = scene_by_ts.get(ts, "")
        results.append(
            {
                "timestamp": ts,
                "scene": scene,
                "prompt": format_image_prompt(ts, scene),
            }
        )
    return results


METADATA_SYSTEM_PROMPT = """You are a YouTube SEO strategist. Given a video topic and \
its full narration script, produce metadata optimized using current YouTube best \
practices (curiosity-driven titles, front-loaded keywords, natural-language \
descriptions with a strong first two lines before the "show more" fold, and a broad \
but relevant tag set).

Respond with ONLY a single JSON object, no commentary, no markdown fences, in exactly \
this shape:
{"titles": ["title 1", "title 2", ... 5 to 8 total viral video title options],
 "description": "a full optimized YouTube video description, plain text",
 "tags": ["tag1", "tag2", ... a generous set of relevant SEO tags]}
"""


def generate_metadata(topic: str, script: str) -> Dict:
    client = _get_client()
    message = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2000,
        system=METADATA_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Video topic: {topic}\n\nFull narration script:\n{script}",
            }
        ],
    )
    raw = "".join(block.text for block in message.content if block.type == "text")
    return _extract_json(raw)
