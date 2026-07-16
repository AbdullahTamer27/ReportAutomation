// Template Manager + Company Manager: register, list, and remove.

import { els, pyapi, escapeHtml, basename, hide } from "./dom.js";
import { state, tmState, cmState } from "./state.js";

// --- Template Manager -------------------------------------------------------
export async function tmPickFile() {
  const api = pyapi();
  if (!api) return tmShowStatus("error", "Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file(["Word templates (*.docx)", "All files (*.*)"]);
  if (p) {
    tmState.filePath = p;
    els.tmFilePath.textContent = p;
    els.tmFilePath.classList.remove("muted");
    // Auto-fill config key from filename if the field is empty.
    if (!els.tmConfigKey.value.trim()) {
      const stem = p.split(/[\\/]/).pop().replace(/\.docx$/i, "");
      const cleaned = stem
        .replace(/^sample_\d+_/i, "")
        .replace(/p/g, ".")
        .replace(/X/g, "×");
      els.tmConfigKey.value = cleaned;
    }
  }
}

export async function tmRegister() {
  const name = els.tmName.value.trim();
  const configKey = els.tmConfigKey.value.trim();
  if (!tmState.filePath) return tmShowStatus("error", "Please choose a .docx file.");
  if (!name) return tmShowStatus("error", "Please enter a display name.");
  if (!configKey) return tmShowStatus("error", "Please enter a configuration key.");

  els.tmRegister.disabled = true;
  els.tmRegister.textContent = "Registering…";
  hide(els.tmStatus);

  try {
    const res = await fetch("/api/templates/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: tmState.filePath, name, config_key: configKey }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      tmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    const verb = data.created ? "registered" : "updated";
    tmShowStatus("success", `✓ Template "${escapeHtml(data.name)}" ${verb} (${escapeHtml(data.config_key)})`);
    els.tmName.value = "";
    els.tmConfigKey.value = "";
    els.tmFilePath.textContent = "No file selected";
    els.tmFilePath.classList.add("muted");
    tmState.filePath = null;
    state.templatesLoaded = false;   // invalidate report dropdown cache
    await tmLoadList();
  } catch (err) {
    tmShowStatus("error", `Request failed: ${err.message || err}`);
  } finally {
    els.tmRegister.disabled = false;
    els.tmRegister.textContent = "Register Template";
  }
}

async function tmDelete(id, name) {
  if (!confirm(`Remove "${name}" from the registry?\n\nThe .docx file is kept on disk.`)) return;
  try {
    const res = await fetch(`/api/templates/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      tmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    state.templatesLoaded = false;
    await tmLoadList();
  } catch (err) {
    tmShowStatus("error", `Delete failed: ${err.message || err}`);
  }
}

export async function tmLoadList() {
  els.tmList.innerHTML = `<p class="tm-empty">Loading…</p>`;
  try {
    const res = await fetch("/api/templates");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = await res.json();
    if (!rows.length) {
      els.tmList.innerHTML = `<p class="tm-empty">No templates registered yet.</p>`;
      return;
    }
    els.tmList.innerHTML = "";
    rows.forEach((t) => {
      const row = document.createElement("div");
      row.className = "tm-row-item";
      row.innerHTML = `
        <div class="tm-info">
          <span class="tm-name">${escapeHtml(t.name)}</span>
          <span class="tm-key">${escapeHtml(t.config_key)}</span>
        </div>
        <button class="secondary tm-del-btn" data-id="${t.id}" data-name="${escapeHtml(t.name)}">Remove</button>`;
      row.querySelector(".tm-del-btn").addEventListener("click", (e) => {
        const btn = e.currentTarget;
        tmDelete(Number(btn.dataset.id), btn.dataset.name);
      });
      els.tmList.appendChild(row);
    });
  } catch (err) {
    els.tmList.innerHTML = `<p class="tm-empty" style="color:var(--error-fg)">Failed to load: ${escapeHtml(err.message)}</p>`;
  }
}

function tmShowStatus(kind, msg) {
  els.tmStatus.hidden = false;
  els.tmStatus.className = `status ${kind}`;
  els.tmStatus.innerHTML = escapeHtml(msg);
}

// --- Company Manager --------------------------------------------------------
export async function cmPickFile() {
  const api = pyapi();
  if (!api) return cmShowStatus("error", "Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file([
    "Image files (*.png;*.jpg;*.jpeg;*.tiff;*.tif;*.bmp;*.gif)",
    "All files (*.*)",
  ]);
  if (p) {
    cmState.filePath = p;
    els.cmFilePath.textContent = p;
    els.cmFilePath.classList.remove("muted");
    if (!els.cmName.value.trim()) {
      els.cmName.value = p.split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
    }
  }
}

export async function cmRegister() {
  const name = els.cmName.value.trim();
  if (!cmState.filePath) return cmShowStatus("error", "Please choose a logo image.");
  if (!name) return cmShowStatus("error", "Please enter a company name.");

  els.cmRegister.disabled = true;
  els.cmRegister.textContent = "Registering…";
  hide(els.cmStatus);

  try {
    const res = await fetch("/api/companies/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_path: cmState.filePath, name }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      cmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    const verb = data.created ? "registered" : "updated";
    cmShowStatus("success", `✓ Company "${escapeHtml(data.name)}" ${verb}`);
    els.cmName.value = "";
    els.cmFilePath.textContent = "No file selected";
    els.cmFilePath.classList.add("muted");
    cmState.filePath = null;
    state.companiesLoaded = false;   // invalidate report dropdown cache
    await cmLoadList();
  } catch (err) {
    cmShowStatus("error", `Request failed: ${err.message || err}`);
  } finally {
    els.cmRegister.disabled = false;
    els.cmRegister.textContent = "Register Company";
  }
}

async function cmDelete(id, name) {
  if (!confirm(`Remove "${name}"?\n\nThe logo file is deleted from disk.`)) return;
  try {
    const res = await fetch(`/api/companies/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      cmShowStatus("error", data.detail || `HTTP ${res.status}`);
      return;
    }
    state.companiesLoaded = false;
    await cmLoadList();
  } catch (err) {
    cmShowStatus("error", `Delete failed: ${err.message || err}`);
  }
}

export async function cmLoadList() {
  els.cmList.innerHTML = `<p class="tm-empty">Loading…</p>`;
  try {
    const res = await fetch("/api/companies");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = await res.json();
    if (!rows.length) {
      els.cmList.innerHTML = `<p class="tm-empty">No companies registered yet.</p>`;
      return;
    }
    els.cmList.innerHTML = "";
    rows.forEach((c) => {
      const row = document.createElement("div");
      row.className = "tm-row-item";
      row.innerHTML = `
        <div class="tm-info">
          <span class="tm-name">${escapeHtml(c.name)}</span>
          <span class="tm-key">${escapeHtml(basename(c.logo_path))}</span>
        </div>
        <button class="secondary tm-del-btn" data-id="${c.id}" data-name="${escapeHtml(c.name)}">Remove</button>`;
      row.querySelector(".tm-del-btn").addEventListener("click", (e) => {
        const btn = e.currentTarget;
        cmDelete(Number(btn.dataset.id), btn.dataset.name);
      });
      els.cmList.appendChild(row);
    });
  } catch (err) {
    els.cmList.innerHTML = `<p class="tm-empty" style="color:var(--error-fg)">Failed to load: ${escapeHtml(err.message)}</p>`;
  }
}

function cmShowStatus(kind, msg) {
  els.cmStatus.hidden = false;
  els.cmStatus.className = `status ${kind}`;
  els.cmStatus.innerHTML = escapeHtml(msg);
}
