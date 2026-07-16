// Ghost Merger: merge ghost-collar intervals in a Joint-Analysis CSV.

import { $, els, pyapi, escapeHtml } from "./dom.js";
import { ghostState } from "./state.js";
import { reveal } from "./generate.js";

export async function pickGhostCsv() {
  const api = pyapi();
  if (!api) return ghostError("Native file dialogs are only available in the desktop app.");
  const p = await api.pick_file(["CSV files (*.csv)", "All files (*.*)"]);
  if (p) {
    ghostState.csvPath = p;
    els.ghostCsvPath.textContent = p;
    els.ghostCsvPath.classList.remove("muted");
  }
}

export async function ghostMerge() {
  if (!ghostState.csvPath) return ghostError("Please choose a Joint-Analysis CSV file.");
  const length = parseFloat(els.ghostLength.value);
  if (!Number.isFinite(length) || length <= 0) {
    return ghostError("Enter a valid ghost collar length greater than 0.");
  }

  setGhostLoading(true);
  ghostStatus("info", `<span class="spinner"></span> Merging ghost collars…`);
  els.ghostPreview.hidden = true;

  try {
    const res = await fetch("/api/ghost/merge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csv_path: ghostState.csvPath, ghost_collar_length: length }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      ghostError(data && data.detail ? data.detail : `HTTP ${res.status}`);
      return;
    }
    ghostSuccess(data);
  } catch (err) {
    ghostError(`Request failed: ${err.message || err}`);
  } finally {
    setGhostLoading(false);
  }
}

// --- Batch: merge every CSV in a folder -------------------------------------
export async function ghostMergeFolder() {
  const api = pyapi();
  if (!api) return ghostError("Native folder dialogs are only available in the desktop app.");
  const length = parseFloat(els.ghostLength.value);
  if (!Number.isFinite(length) || length <= 0) {
    return ghostError("Enter a valid ghost collar length greater than 0.");
  }
  const folder = await api.pick_folder();
  if (!folder) return;

  setGhostLoading(true);
  ghostStatus("info", `<span class="spinner"></span> Merging every CSV in the folder…`);
  els.ghostPreview.hidden = true;

  try {
    const res = await fetch("/api/ghost/merge-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder_path: folder, ghost_collar_length: length }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      ghostError(data && data.detail ? data.detail : `HTTP ${res.status}`);
      return;
    }
    ghostFolderSuccess(data);
  } catch (err) {
    ghostError(`Request failed: ${err.message || err}`);
  } finally {
    setGhostLoading(false);
  }
}

function ghostFolderSuccess(data) {
  const items = (data.results || []).map((r) =>
    r.ok
      ? `<li class="note-info">✓ ${escapeHtml(r.file)} — ${r.input_rows}→${r.output_rows} rows, ${r.merged_chains} chain(s)</li>`
      : `<li class="note-error">✗ ${escapeHtml(r.file)} — ${escapeHtml(r.error || "failed")}</li>`
  ).join("");
  ghostStatus(
    data.failed ? "info" : "success",
    `<strong>Folder merge complete — ${data.succeeded} ok${data.failed ? `, ${data.failed} failed` : ""}</strong>
     <div class="iv-summary">collars ≥ ${data.threshold} ft • a merged_*.xlsx was written beside each CSV</div>
     <ul class="notes-list">${items}</ul>
     <button id="ghostRevealFolderBtn" type="button" class="secondary">Reveal a result</button>`
  );
  const first = (data.results || []).find((r) => r.ok && r.output_path);
  const btn = $("ghostRevealFolderBtn");
  if (btn && first) btn.addEventListener("click", () => reveal(first.output_path));
}

function ghostSuccess(data) {
  ghostStatus(
    "success",
    `<strong>Merged file saved</strong>
     <div class="result-path">${escapeHtml(data.output_path)}</div>
     <div class="iv-summary">${data.input_rows} joints → ${data.output_rows} rows • ${data.merged_chains} merged chain(s) • collars ≥ ${data.threshold} ft</div>
     <button id="ghostRevealBtn" type="button" class="secondary">Reveal in file manager</button>`
  );
  const btn = $("ghostRevealBtn");
  if (btn) btn.addEventListener("click", () => reveal(data.output_path));
  els.ghostPreview.hidden = false;
  els.ghostPreview.textContent = data.preview;
}

function ghostStatus(kind, html) {
  els.ghostStatus.hidden = false;
  els.ghostStatus.className = `status ${kind}`;
  els.ghostStatus.innerHTML = html;
}
function ghostError(msg) {
  ghostStatus("error", `<strong>Error:</strong> ${escapeHtml(msg)}`);
}
function setGhostLoading(loading) {
  els.ghostMerge.disabled = loading;
  els.pickGhostCsv.disabled = loading;
  if (els.ghostPickFolder) els.ghostPickFolder.disabled = loading;
  els.ghostMerge.textContent = loading ? "Working…" : "Merge & Export";
}
