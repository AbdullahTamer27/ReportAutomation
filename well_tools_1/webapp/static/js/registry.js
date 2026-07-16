// Template + company registries: load, populate the dropdowns, resolve the
// current selection, and gate the Generate button.

import { els } from "./dom.js";
import { state } from "./state.js";

// --- Templates --------------------------------------------------------------
export async function ensureTemplates() {
  if (state.templatesLoaded) return;
  const res = await fetch("/api/templates");
  if (!res.ok) throw new Error(`Failed to load templates (HTTP ${res.status})`);
  state.templates = await res.json();
  state.templatesLoaded = true;
  populateTemplateOptions();
}

function populateTemplateOptions() {
  els.templateSelect.innerHTML = "";
  for (const t of state.templates) {
    const opt = document.createElement("option");
    opt.value = String(t.id);
    opt.textContent = t.config_key ? `${t.name} — ${t.config_key}` : t.name;
    els.templateSelect.appendChild(opt);
  }
  if (els.templatePickHint) {
    els.templatePickHint.textContent = state.templates.length
      ? "" : "No templates registered — add one in the Template Manager.";
    els.templatePickHint.classList.toggle("hint-warn", state.templates.length === 0);
  }
}

export function resolveTemplate() {
  const id = parseInt(els.templateSelect.value, 10);
  return state.templates.find((t) => t.id === id) || null;
}

export function refreshTemplateHint() {
  const t = resolveTemplate();
  if (els.templateHint) {
    els.templateHint.textContent = t ? `Template: ${t.name}` : "";
    els.templateHint.classList.remove("hint-warn");
  }
  updateGenerateEnabled();
}

// --- Companies --------------------------------------------------------------
export async function ensureCompanies() {
  if (state.companiesLoaded) return;
  const res = await fetch("/api/companies");
  if (!res.ok) throw new Error(`Failed to load companies (HTTP ${res.status})`);
  state.companies = await res.json();
  state.companiesLoaded = true;
  populateCompanyOptions();
}

function populateCompanyOptions() {
  els.company.innerHTML = "";
  for (const c of state.companies) {
    const opt = document.createElement("option");
    opt.value = String(c.id);
    opt.textContent = c.name;
    els.company.appendChild(opt);
  }
  refreshCompanyHint();
}

export function resolveCompany() {
  const id = parseInt(els.company.value, 10);
  return state.companies.find((c) => c.id === id) || null;
}

export function refreshCompanyHint() {
  if (els.companyHint) {
    if (!state.companies.length) {
      els.companyHint.textContent =
        "No companies registered — add one in the Company Manager before generating.";
      els.companyHint.classList.add("hint-warn");
    } else {
      els.companyHint.textContent = "";
      els.companyHint.classList.remove("hint-warn");
    }
  }
  updateGenerateEnabled();
}

// --- Config value + Generate gating -----------------------------------------
export function configValue() {
  return (els.configInput.value || "").trim();
}

export function updateGenerateEnabled() {
  els.generate.disabled =
    !(resolveTemplate() && resolveCompany() && configValue() && state.configOk);
}
