const STATUS_ORDER = [
  "created",
  "script_ready",
  "transcript_ready",
  "prompts_ready",
  "images_ready",
  "video_ready",
  "complete",
];

// Each "shows completed output" step is paired with the step whose action it
// unlocks, at the same status rank - e.g. once the script exists (rank 1), both
// viewing the script AND starting the audio upload become available together.
const STEP_REQUIREMENT = {
  "step-topic": 0,
  "step-script": 1,
  "step-audio": 1,
  "step-transcript": 2,
  "step-prompts": 2,
  "step-images": 3,
  "step-video": 5,
  "step-metadata": 5,
};

let currentSlug = null;

const $ = (id) => document.getElementById(id);

function normalizeStatus(status) {
  if (status === "images_partial") return "images_ready";
  return status || "created";
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function showNotice(id, message, isError) {
  const el = $(id);
  el.textContent = message;
  el.classList.remove("hidden");
  el.classList.toggle("error", !!isError);
}

function hideNotice(id) {
  $(id).classList.add("hidden");
}

async function loadProjects() {
  const projects = await api("/api/projects");
  const list = $("project-list");
  list.innerHTML = "";
  projects.forEach((p) => {
    const li = document.createElement("li");
    li.textContent = p.title || p.topic || p.slug;
    li.dataset.slug = p.slug;
    if (p.slug === currentSlug) li.classList.add("active");
    li.addEventListener("click", () => selectProject(p.slug));
    list.appendChild(li);
  });
}

function resetWorkspace() {
  currentSlug = null;
  $("empty-state").classList.add("hidden");
  $("workspace").classList.remove("hidden");
  $("topic-input").value = "";
  hideNotice("topic-error");

  $("video-title").textContent = "";
  $("video-title").classList.add("hidden");
  $("script-preview").value = "";
  $("transcript-preview").value = "";
  $("prompts-preview").value = "";
  $("image-grid").innerHTML = "";
  $("video-player").src = "";
  $("titles-list").innerHTML = "";
  $("description-preview").value = "";
  $("tags-list").innerHTML = "";
  hideNotice("images-status");
  hideNotice("assemble-status");
  hideNotice("audio-status");

  Object.keys(STEP_REQUIREMENT).forEach((stepId) => {
    $(stepId).classList.remove("active", "done");
  });
  $("step-topic").classList.add("active");
}

async function selectProject(slug) {
  currentSlug = slug;
  const state = await api(`/api/projects/${slug}`);
  render(state);
  await loadProjects();
}

function render(state) {
  $("empty-state").classList.add("hidden");
  $("workspace").classList.remove("hidden");

  const rank = STATUS_ORDER.indexOf(normalizeStatus(state.status));

  Object.entries(STEP_REQUIREMENT).forEach(([stepId, requirement]) => {
    const el = $(stepId);
    el.classList.remove("active", "done");
    if (rank > requirement) {
      el.classList.add("done");
    } else if (rank === requirement) {
      el.classList.add("active");
    }
  });

  if (state.title) {
    $("video-title").textContent = state.title;
    $("video-title").classList.remove("hidden");
  }

  if (state.topic) $("topic-input").value = state.topic;
  if (state.script) $("script-preview").value = state.script;

  if (state.timestamped_lines) {
    $("transcript-preview").value = state.timestamped_lines
      .map((l) => `[${l.timestamp}] ${l.text}`)
      .join("\n\n");
  }

  if (state.image_prompts) {
    $("prompts-preview").value = state.image_prompts.map((p) => p.prompt).join("\n\n");
  }

  if (state.images) {
    const grid = $("image-grid");
    grid.innerHTML = "";
    state.images.forEach((img) => {
      if (!img) return;
      const fig = document.createElement("figure");
      const image = document.createElement("img");
      image.src = `/files/${state.slug}/images/${img.file}`;
      const caption = document.createElement("figcaption");
      caption.textContent = img.timestamp;
      fig.appendChild(image);
      fig.appendChild(caption);
      grid.appendChild(fig);
    });
    if (state.image_errors && state.image_errors.length) {
      showNotice(
        "images-status",
        `${state.image_errors.length} image(s) failed to generate. You can click "Generate Images Automatically" again to retry.`,
        true
      );
    } else {
      hideNotice("images-status");
    }
  }

  if (state.video_file) {
    $("video-player").src = `/files/${state.slug}/${state.video_file}`;
  }

  if (state.titles) {
    const titlesList = $("titles-list");
    titlesList.innerHTML = "";
    state.titles.forEach((title) => {
      const row = document.createElement("div");
      row.className = "title-option";
      const span = document.createElement("span");
      span.textContent = title;
      const btn = document.createElement("button");
      btn.className = "secondary";
      btn.textContent = "Copy";
      btn.addEventListener("click", () => navigator.clipboard.writeText(title));
      row.appendChild(span);
      row.appendChild(btn);
      titlesList.appendChild(row);
    });
  }

  if (state.description !== undefined) {
    $("description-preview").value = state.description;
  }

  if (state.tags) {
    const tagsList = $("tags-list");
    tagsList.innerHTML = "";
    state.tags.forEach((tag) => {
      const span = document.createElement("span");
      span.textContent = tag;
      tagsList.appendChild(span);
    });
  }
}

$("new-project-btn").addEventListener("click", resetWorkspace);

$("generate-script-btn").addEventListener("click", async () => {
  const topic = $("topic-input").value.trim();
  if (!topic) {
    showNotice("topic-error", "Please enter a video topic.", true);
    return;
  }
  hideNotice("topic-error");
  const btn = $("generate-script-btn");
  btn.disabled = true;
  btn.textContent = "Generating script...";
  try {
    const state = await api("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    currentSlug = state.slug;
    render(state);
    await loadProjects();
  } catch (err) {
    showNotice("topic-error", err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Script";
  }
});

$("download-script-btn").addEventListener("click", () => {
  window.open(`/api/projects/${currentSlug}/download/script_${currentSlug}.txt`, "_blank");
});

$("transcribe-btn").addEventListener("click", async () => {
  const fileInput = $("audio-input");
  if (!fileInput.files.length) {
    showNotice("audio-status", "Choose an audio file first.", true);
    return;
  }
  const btn = $("transcribe-btn");
  btn.disabled = true;
  showNotice("audio-status", "Transcribing audio locally, this can take a minute...", false);
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  try {
    const state = await api(`/api/projects/${currentSlug}/audio`, {
      method: "POST",
      body: formData,
    });
    hideNotice("audio-status");
    render(state);
  } catch (err) {
    showNotice("audio-status", err.message, true);
  } finally {
    btn.disabled = false;
  }
});

$("download-transcript-btn").addEventListener("click", () => {
  window.open(`/api/projects/${currentSlug}/download/transcript_${currentSlug}.txt`, "_blank");
});

$("generate-prompts-btn").addEventListener("click", async () => {
  const btn = $("generate-prompts-btn");
  btn.disabled = true;
  btn.textContent = "Generating prompts...";
  try {
    const state = await api(`/api/projects/${currentSlug}/image-prompts`, { method: "POST" });
    render(state);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Image Prompts";
  }
});

$("download-prompts-btn").addEventListener("click", () => {
  window.open(`/api/projects/${currentSlug}/download/image_prompts_${currentSlug}.txt`, "_blank");
});

$("upload-images-btn").addEventListener("click", async () => {
  const fileInput = $("images-input");
  if (!fileInput.files.length) {
    showNotice("images-status", "Choose the images you generated in Google Flow first.", true);
    return;
  }
  const btn = $("upload-images-btn");
  btn.disabled = true;
  showNotice("images-status", `Uploading ${fileInput.files.length} image(s)...`, false);
  const formData = new FormData();
  Array.from(fileInput.files).forEach((file) => formData.append("files", file));
  try {
    const state = await api(`/api/projects/${currentSlug}/images/upload`, {
      method: "POST",
      body: formData,
    });
    hideNotice("images-status");
    render(state);
  } catch (err) {
    showNotice("images-status", err.message, true);
  } finally {
    btn.disabled = false;
  }
});

$("assemble-btn").addEventListener("click", async () => {
  const btn = $("assemble-btn");
  btn.disabled = true;
  showNotice("assemble-status", "Assembling video with ffmpeg...", false);
  try {
    const state = await api(`/api/projects/${currentSlug}/assemble`, { method: "POST" });
    hideNotice("assemble-status");
    render(state);
  } catch (err) {
    showNotice("assemble-status", err.message, true);
  } finally {
    btn.disabled = false;
  }
});

$("download-video-btn").addEventListener("click", () => {
  window.open(`/api/projects/${currentSlug}/download/final_${currentSlug}.mp4`, "_blank");
});

$("generate-metadata-btn").addEventListener("click", async () => {
  const btn = $("generate-metadata-btn");
  btn.disabled = true;
  btn.textContent = "Generating...";
  try {
    const state = await api(`/api/projects/${currentSlug}/metadata`, { method: "POST" });
    render(state);
  } catch (err) {
    alert(err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Titles, Description & Tags";
  }
});

$("copy-description-btn").addEventListener("click", () => {
  navigator.clipboard.writeText($("description-preview").value);
});

$("copy-tags-btn").addEventListener("click", () => {
  const tags = Array.from($("tags-list").children).map((s) => s.textContent);
  navigator.clipboard.writeText(tags.join(", "));
});

loadProjects();

api("/api/version")
  .then((info) => {
    if (!info.update_available) return;
    const banner = $("update-banner");
    banner.innerHTML = "";
    banner.classList.remove("hidden");
    const text = document.createElement("span");
    text.textContent = `A new version (${info.latest_version}) is available. `;
    const link = document.createElement("a");
    link.href = info.download_url;
    link.textContent = "Download it";
    link.target = "_blank";
    link.style.color = "inherit";
    banner.appendChild(text);
    banner.appendChild(link);
  })
  .catch(() => {});
