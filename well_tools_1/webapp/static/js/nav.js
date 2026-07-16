// View navigation. Swaps the visible .view section and moves focus to its
// heading so keyboard / screen-reader users don't lose their place.

import { tmLoadList } from "./managers.js";
import { cmLoadList } from "./managers.js";

const VIEWS = ["mode", "ghost", "inputs", "workspace", "templates", "companies"];

export function showView(name) {
  for (const v of VIEWS) {
    const el = document.getElementById(`view-${v}`);
    if (el) el.hidden = v !== name;
  }
  if (name === "templates") tmLoadList();
  if (name === "companies") cmLoadList();

  // A11y: move focus to the new view's heading.
  const active = document.getElementById(`view-${name}`);
  const heading = active && active.querySelector("h1");
  if (heading) {
    if (!heading.hasAttribute("tabindex")) heading.setAttribute("tabindex", "-1");
    heading.focus({ preventScroll: true });
  }
  // Keep the brand top bar in sync with the current tool.
  const context = document.getElementById("brandContext");
  if (context) context.textContent = CONTEXT_LABEL[name] || "";
}

const CONTEXT_LABEL = {
  mode: "",
  ghost: "Ghost Merger",
  inputs: "Report Automation",
  workspace: "Report Automation",
  templates: "Template Manager",
  companies: "Company Manager",
};
