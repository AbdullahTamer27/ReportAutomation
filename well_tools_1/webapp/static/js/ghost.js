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
  els.ghostMerge.textContent = loading ? "Working…" : "Merge & Export";
}
