// In-app updater UI. On boot, asks the backend for the launch decision and
// renders it: a dismissable banner (optional), a mandatory modal (required), or
// a full blocking screen (killed / blocked). "Update now" triggers the backend
// download + swap-restart.

import { escapeHtml } from "./dom.js";

const DISMISS_KEY = "talos_dismissed_version";

export async function checkForUpdates() {
  let d;
  try {
    const res = await fetch("/api/update/check");
    if (!res.ok) return;                 // endpoint missing / older build → silent
    d = await res.json();
  } catch (_e) {
    return;                              // offline → nothing to show
  }
  render(d);
}

function render(d) {
  if (d.status === "blocked") return showBlocked(d);
  if (d.status === "update_required") return showModal(d, /*required*/ true);
  if (d.status === "update_optional") {
    if (localStorage.getItem(DISMISS_KEY) === d.latest) return;  // user said "Later"
    return showBanner(d);
  }
  // "ok" → nothing to do.
}

// --- Optional: a dismissable banner under the top bar -----------------------
function showBanner(d) {
  document.getElementById("updateBanner")?.remove();
  const bar = document.createElement("div");
  bar.id = "updateBanner";
  bar.className = "update-banner";
  bar.setAttribute("role", "status");
  bar.innerHTML = `
    <span class="update-dot"></span>
    <span class="update-text">Talos <strong>${escapeHtml(d.latest)}</strong> is available
      <span class="update-cur">(you're on ${escapeHtml(d.current)})</span></span>
    <span class="update-spacer"></span>
    <button type="button" class="update-now primary-sm">Update now</button>
    <button type="button" class="update-later secondary-sm">Later</button>`;
  bar.querySelector(".update-now").addEventListener("click", () => applyUpdate(bar));
  bar.querySelector(".update-later").addEventListener("click", () => {
    localStorage.setItem(DISMISS_KEY, d.latest);
    bar.remove();
  });
  document.body.appendChild(bar);
}

// --- Required: a modal that can't be dismissed ------------------------------
function showModal(d, required) {
  const ov = overlay("updateModal");
  ov.innerHTML = `
    <div class="update-card">
      <span class="brand-mark" aria-hidden="true"></span>
      <h2>Update required</h2>
      <p>A required update to <strong>Talos ${escapeHtml(d.latest)}</strong> must be installed
         to keep using the app <span class="update-cur">(you're on ${escapeHtml(d.current)})</span>.</p>
      ${d.message ? `<p class="update-msg">${escapeHtml(d.message)}</p>` : ""}
      <div class="update-actions"><button type="button" class="update-now primary">Update now</button></div>
      <div class="update-progress" hidden></div>
    </div>`;
  ov.querySelector(".update-now").addEventListener("click", () => applyUpdate(ov));
  document.body.appendChild(ov);
}

// --- Blocked / killed: a full screen, no way past ---------------------------
function showBlocked(d) {
  const ov = overlay("updateBlocked");
  ov.innerHTML = `
    <div class="update-card update-card--blocked">
      <span class="brand-mark" aria-hidden="true"></span>
      <h2>Access disabled</h2>
      <p>${escapeHtml(d.message || "This copy of Talos has been disabled. Contact the admin.")}</p>
      <p class="update-cur">Version ${escapeHtml(d.current)}</p>
    </div>`;
  document.body.appendChild(ov);
}

function overlay(id) {
  document.getElementById(id)?.remove();
  const ov = document.createElement("div");
  ov.id = id;
  ov.className = "update-overlay";
  ov.setAttribute("role", "dialog");
  ov.setAttribute("aria-modal", "true");
  return ov;
}

// --- Apply (download → verify → swap-restart) -------------------------------
async function applyUpdate(host) {
  const progress = host.querySelector(".update-progress");
  const buttons = host.querySelectorAll("button");
  buttons.forEach((b) => (b.disabled = true));
  if (progress) {
    progress.hidden = false;
    progress.innerHTML = `<span class="spinner"></span> Downloading… the app will restart automatically.`;
  } else {
    host.querySelector(".update-text").innerHTML =
      `<span class="spinner"></span> Downloading… the app will restart.`;
  }
  try {
    const res = await fetch("/api/update/apply", { method: "POST" });
    // On the packaged build this process exits mid-swap and the fetch never
    // resolves — that's success. We only get here on a handled error.
    const data = await res.json().catch(() => ({}));
    const msg = data.detail || `Update failed (HTTP ${res.status}).`;
    if (progress) progress.innerHTML = escapeHtml(msg);
    else host.querySelector(".update-text").textContent = msg;
    buttons.forEach((b) => (b.disabled = false));
  } catch (_e) {
    // Connection dropped = the app is restarting into the new build. Nothing to do.
  }
}
