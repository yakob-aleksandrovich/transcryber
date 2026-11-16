"use strict";

const $ = (id) => document.getElementById(id);

const fileInput = $("file-input");
const dropzone = $("dropzone");
const dropzoneText = $("dropzone-text");
const form = $("upload-form");
const submitBtn = $("submit-btn");
const progress = $("progress");
const progressText = $("progress-text");
const errorEl = $("error");
const listEl = $("transcript-list");
const emptyEl = $("empty");

let selectedFile = null;
let currentViewerId = null;

// ---- Auth / view switching --------------------------------------------
function showLogin() {
  $("login").hidden = false;
  $("app").hidden = true;
  $("user-box").hidden = true;
  $("model-info").textContent = "";
}

function showApp(username) {
  $("login").hidden = true;
  $("app").hidden = false;
  $("user-box").hidden = false;
  $("username").textContent = username;
}

$("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("login-error").hidden = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("login-username").value,
        password: $("login-password").value,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Login failed");
    }
    $("login-password").value = "";
    await init();
  } catch (err) {
    $("login-error").textContent = err.message;
    $("login-error").hidden = false;
  }
});

$("logout-btn").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  showLogin();
});

// Wrapper that bounces to the login screen on 401.
async function api(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    showLogin();
    throw new Error("Session expired — please sign in again.");
  }
  return res;
}

// ---- File selection ----------------------------------------------------
function setFile(file) {
  selectedFile = file || null;
  if (selectedFile) {
    dropzoneText.textContent = selectedFile.name;
    dropzone.classList.add("has-file");
    submitBtn.disabled = false;
  } else {
    dropzoneText.textContent = "Click to choose a file, or drop it here";
    dropzone.classList.remove("has-file");
    submitBtn.disabled = true;
  }
}

fileInput.addEventListener("change", () => setFile(fileInput.files[0]));

["dragover", "dragenter"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    fileInput.files = e.dataTransfer.files;
    setFile(file);
  }
});

// ---- Upload + poll -----------------------------------------------------
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selectedFile) return;

  errorEl.hidden = true;
  submitBtn.disabled = true;
  progress.hidden = false;
  progressText.textContent = "Uploading…";

  try {
    const body = new FormData();
    body.append("file", selectedFile);
    const res = await api("/api/transcribe", { method: "POST", body });
    if (!res.ok) throw new Error((await res.json()).detail || "Upload failed");
    const { job_id } = await res.json();
    await pollJob(job_id);
  } catch (err) {
    showError(err.message);
  } finally {
    progress.hidden = true;
    submitBtn.disabled = false;
  }
});

function pollJob(jobId) {
  return new Promise((resolve, reject) => {
    const timer = setInterval(async () => {
      try {
        const res = await api(`/api/jobs/${jobId}`);
        const job = await res.json();
        if (job.status === "processing") {
          progressText.textContent = "Transcribing… (this can take a while on CPU)";
        } else if (job.status === "done") {
          clearInterval(timer);
          setFile(null);
          fileInput.value = "";
          await loadTranscripts();
          resolve();
        } else if (job.status === "error") {
          clearInterval(timer);
          reject(new Error(job.error || "Transcription failed"));
        }
      } catch (err) {
        clearInterval(timer);
        reject(err);
      }
    }, 1500);
  });
}

function showError(msg) {
  errorEl.textContent = msg;
  errorEl.hidden = false;
}

// ---- Transcript list ---------------------------------------------------
function fmtMeta(t) {
  const bits = [];
  if (t.created_at) bits.push(new Date(t.created_at).toLocaleString());
  if (t.language) bits.push(t.language);
  if (t.duration) bits.push(`${Math.round(t.duration)}s`);
  return bits.join(" · ");
}

async function loadTranscripts() {
  const res = await api("/api/transcripts");
  const items = await res.json();
  listEl.innerHTML = "";
  emptyEl.hidden = items.length > 0;

  for (const t of items) {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="t-name"></div>
      <div class="t-meta"></div>
      <div class="t-preview"></div>`;
    li.querySelector(".t-name").textContent = t.original_name || "(untitled)";
    li.querySelector(".t-meta").textContent = fmtMeta(t);
    li.querySelector(".t-preview").textContent = t.preview || "";
    li.addEventListener("click", () => openViewer(t.id));
    listEl.appendChild(li);
  }
}

$("refresh-btn").addEventListener("click", loadTranscripts);

// ---- Viewer ------------------------------------------------------------
async function openViewer(id) {
  const res = await api(`/api/transcripts/${id}`);
  if (!res.ok) return;
  const rec = await res.json();
  currentViewerId = id;
  $("viewer-title").textContent = rec.original_name || "Transcript";
  $("viewer-meta").textContent = fmtMeta(rec);
  $("viewer-text").textContent = rec.text || "(empty)";
  $("viewer-download").href = `/api/transcripts/${id}/download`;
  $("viewer").hidden = false;
}

function closeViewer() {
  $("viewer").hidden = true;
  currentViewerId = null;
}

$("viewer-close").addEventListener("click", closeViewer);
$("viewer").addEventListener("click", (e) => {
  if (e.target === $("viewer")) closeViewer();
});

$("viewer-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("viewer-text").textContent);
    $("viewer-copy").textContent = "Copied!";
    setTimeout(() => ($("viewer-copy").textContent = "Copy"), 1500);
  } catch {
    /* clipboard may be blocked; ignore */
  }
});

$("viewer-delete").addEventListener("click", async () => {
  if (!currentViewerId) return;
  await api(`/api/transcripts/${currentViewerId}`, { method: "DELETE" });
  closeViewer();
  await loadTranscripts();
});

// ---- Init --------------------------------------------------------------
async function init() {
  // Are we logged in?
  const meRes = await fetch("/api/me");
  if (meRes.status === 401) {
    showLogin();
    return;
  }
  const me = await meRes.json();
  showApp(me.username);

  try {
    const res = await api("/api/status");
    const s = await res.json();
    $("model-info").textContent = `model: ${s.model} · ${s.device}/${s.compute_type}`;
  } catch {
    /* non-fatal */
  }
  await loadTranscripts();
}

init();
