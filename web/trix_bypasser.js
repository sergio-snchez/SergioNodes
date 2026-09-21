const UPSTREAM = ["Trix Bypass", "https://github.com/buserror/comfyui-trixnodes", "TrixBypasser"];

import { app } from "../../scripts/app.js";

/** Trix Bypass nodes, ported into SergioNodes for the modern (Nodes 2.0)
 *  frontend. The backend keeps the same type names so old workflows keep
 *  resolving; disable comfyui-trixnodes so its extension no longer fights over
 *  the same node types. */

const NODE_TYPES = ["TrixBypasser", "TrixBypasserSimple"];

const TRIX_CSS = `
.sergio-trix { display:flex; flex-direction:column; width:100%; height:100%;
  font-size:12px; color:#d7d7df; user-select:none; min-width:280px; }
.sergio-trix-header { display:flex; align-items:center; gap:6px; padding:5px 6px; }
.sergio-trix-btn { background:rgba(255,255,255,.07); color:#d7d7df; border:1px solid
  rgba(255,255,255,.15); border-radius:5px; padding:2px 8px; font-size:11px;
  cursor:pointer; white-space:nowrap; }
.sergio-trix-btn:hover { background:rgba(255,255,255,.14); }
.sergio-trix-list { flex:1; overflow-y:auto; padding:0 4px 6px; }
.sergio-trix-row { display:flex; align-items:center; gap:6px; padding:2px 6px;
  border-radius:4px; color:#d0d0da; }
.sergio-trix-row:hover { background:rgba(255,255,255,.07); }
.sergio-trix-row.groups { padding-left:14px; }
.sergio-trix-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.sergio-trix-name.empty { color:#6b6b78; font-style:italic; }
.sergio-trix-ico { background:rgba(255,255,255,.09); border:none; border-radius:4px;
  color:#c8c8d4; font-size:11px; line-height:16px; width:18px; height:18px;
  padding:0; cursor:pointer; text-align:center; }
.sergio-trix-ico:hover { background:rgba(255,255,255,.2); }
.sergio-trix-ico.del:hover { background:#a03a3a; color:#fff; }
.sergio-trix-sw { width:26px; height:14px; border-radius:7px; background:rgba(255,255,255,.14);
  position:relative; cursor:pointer; flex:none; }
.sergio-trix-sw .knob { position:absolute; top:1px; left:1px; width:12px; height:12px;
  border-radius:50%; background:#9a9aa6; transition:left .12s, background .12s; }
.sergio-trix-sw.on { background:#387aff; }
.sergio-trix-sw.on .knob { left:13px; background:#fff; }
.sergio-trix-groupname { flex:1; background:transparent; border:none; outline:none;
  color:#e3e3ec; font-size:12px; padding:2px 0; min-width:40px; }
.sergio-trix-arrow { width:14px; text-align:center; color:#88889a; cursor:pointer; flex:none; }
.sergio-trix-empty { padding:8px 10px; color:#6b6b78; font-style:italic; }
.sergio-trix-overlay { position:fixed; inset:0; background:rgba(10,10,12,.7);
  z-index:10000; display:flex; align-items:center; justify-content:center; }
.sergio-trix-picker { background:#202026; border:1px solid rgba(255,255,255,.14);
  border-radius:8px; min-width:400px; max-width:70vw; max-height:70vh;
  display:flex; flex-direction:column; padding:10px; gap:8px; }
.sergio-trix-picker .p-head { font-weight:600; }
.sergio-trix-picker input { background:#17171b; border:1px solid rgba(255,255,255,.14);
  color:#e3e3ec; border-radius:5px; padding:4px 8px; font-size:12px; outline:none; }
.sergio-trix-picker .p-list { overflow-y:auto; max-height:50vh; }
.sergio-trix-picker .p-row { padding:4px 8px; border-radius:4px; cursor:pointer;
  display:flex; justify-content:space-between; gap:10px; }
.sergio-trix-picker .p-row:hover { background:rgba(255,255,255,.08); }
.sergio-trix-picker .p-row.sel { background:rgba(56,122,255,.28); }
.sergio-trix-picker .p-row .sub { color:#8a8a98; font-size:11px; }
.sergio-trix-picker .p-foot { display:flex; justify-content:flex-end; gap:6px; }
`;

function injectCss() {
  if (document.getElementById("sergio-trix-css")) return;
  const style = document.createElement("style");
  style.id = "sergio-trix-css";
  style.textContent = TRIX_CSS;
  document.head.appendChild(style);
}

function findNodeById(id) {
  const g = app.graph;
  if (!g) return null;
  if (typeof g.getNodeById === "function") return g.getNodeById(id);
  return (g._nodes || []).find((n) => String(n.id) === String(id));
}

function nodeLabel(node) {
  return node.title || node.type || "node";
}

function targetIds(target) {
  return (target.value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function defaultState(isSimple) {
  if (isSimple) {
    return {
      version: 1, selectMode: "multi", muteMode: "bypass", deleteMode: false,
      targets: []
    };
  }
  return {
    version: 1, selectMode: "multi", muteMode: "bypass", deleteMode: false,
    groups: []
  };
}

/** Applies the wanted bypass/mute modes to the target nodes and restores the
 *  ones that stopped being targeted. Same semantics as the original pack:
 *  0 = normal, 2 = muted, 4 = bypass. */
function trixEnforce(node) {
  const state = node.properties && node.properties.trixBypasserState;
  if (!state) return;
  const isSimple = node.type === "TrixBypasserSimple";
  const wanted = new Map();

  const claim = (id, mode) => {
    if (wanted.has(id)) {
      const prev = wanted.get(id);
      if (prev !== 0 && mode === 0) wanted.set(id, 0);
    } else {
      wanted.set(id, mode);
    }
  };

  if (isSimple) {
    for (const target of state.targets || []) {
      if (!target.value || !target.value.trim()) continue;
      let active = target.active;
      if (state.selectMode === "single") {
        const activeTarget = (state.targets || []).find((t) => t.active);
        active = activeTarget === target;
      }
      const mode = active ? 0 : (state.muteMode === "mute" ? 2 : 4);
      for (const id of targetIds(target)) claim(id, mode);
    }
  } else {
    for (const group of state.groups || []) {
      let groupActive = group.active;
      if (state.selectMode === "single") {
        const activeGroup = (state.groups || []).find((g) => g.active);
        groupActive = !!activeGroup && activeGroup.id === group.id;
      }
      for (const target of group.targets || []) {
        if (!target.value || !target.value.trim()) continue;
        const mode = (groupActive && target.active) ? 0 : (state.muteMode === "mute" ? 2 : 4);
        for (const id of targetIds(target)) claim(id, mode);
      }
    }
  }

  const originals = node.properties.trixBypasserOriginalModes ||
      (node.properties.trixBypasserOriginalModes = {});

  for (const [id, oldMode] of Object.entries(originals)) {
    if (!wanted.has(id)) {
      const t = findNodeById(id);
      if (t) {
        t.mode = oldMode;
        if (t.setDirtyCanvas) t.setDirtyCanvas(true, true);
      }
      delete originals[id];
    }
  }

  let changed = false;
  for (const [id, mode] of wanted) {
    const t = findNodeById(id);
    if (!t) continue;
    if (!(id in originals)) originals[id] = t.mode;
    if (t.mode !== mode) {
      t.mode = mode;
      if (t.setDirtyCanvas) t.setDirtyCanvas(true, true);
      changed = true;
    }
  }
  if (changed && app.canvas) app.canvas.setDirty(true, true);
}

function restoreAll(node) {
  const originals = node.properties && node.properties.trixBypasserOriginalModes;
  if (!originals) return;
  for (const [id, mode] of Object.entries(originals)) {
    const t = findNodeById(id);
    if (t) {
      t.mode = mode;
      if (t.setDirtyCanvas) t.setDirtyCanvas(true, true);
    }
  }
  if (app.canvas) app.canvas.setDirty(true, true);
}

function makeSwitch(active, onChange) {
  const sw = document.createElement("div");
  sw.className = "sergio-trix-sw" + (active ? " on" : "");
  sw.innerHTML = '<div class="knob"></div>';
  sw.addEventListener("click", (e) => {
    e.stopPropagation();
    onChange(!active);
  });
  return sw;
}

function makeButton(text, cls, onClick) {
  const b = document.createElement("button");
  b.className = "sergio-trix-btn" + (cls ? " " + cls : "");
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

function centerOnTarget(node) {
  const ids = targetIds(node);
  let t = null;
  for (const id of ids) {
    t = findNodeById(id);
    if (t) break;
  }
  if (t && app.canvas) {
    try {
      app.canvas.centerOnNode(t);
    } catch (e) { /* not critical */ }
    app.canvas.setDirty(true, true);
  }
}

function openPicker(node, onPick) {
  const cands = (app.graph?._nodes || []).filter(
    (n) => n.id !== node.id && !NODE_TYPES.includes(n.type));
  const overlay = document.createElement("div");
  overlay.className = "sergio-trix-overlay";

  const box = document.createElement("div");
  box.className = "sergio-trix-picker";

  const head = document.createElement("div");
  head.className = "p-head";
  head.textContent = `Pick targets — ${cands.length} nodes on canvas`;

  const search = document.createElement("input");
  search.placeholder = "Filter…";

  const list = document.createElement("div");
  list.className = "p-list";
  const selected = new Set();

  const updateFoot = () => {
    footLabel.textContent = selected.size ? `Add (${selected.size})` : "Add";
  };

  const rows = cands.map((n) => {
    const row = document.createElement("div");
    row.className = "p-row";
    row.dataset.key = `${nodeLabel(n)} ${n.type} ${n.id}`.toLowerCase();
    const title = document.createElement("span");
    title.textContent = nodeLabel(n);
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = `${n.type} · ${n.id}`;
    row.appendChild(title);
    row.appendChild(sub);
    row.addEventListener("click", () => {
      if (selected.has(n)) {
        selected.delete(n);
        row.classList.remove("sel");
      } else {
        selected.add(n);
        row.classList.add("sel");
      }
      updateFoot();
    });
    return row;
  });

  const filter = () => {
    const q = search.value.toLowerCase();
    list.replaceChildren(...rows.filter(
      (r) => q === "" || (r.dataset.key || "").includes(q)));
  };
  search.addEventListener("input", filter);

  const foot = document.createElement("div");
  foot.className = "p-foot";
  const footLabel = document.createElement("span");
  const cancel = makeButton("Cancel", "", () => overlay.remove());
  const add = makeButton("Add", "", () => {
    overlay.remove();
    onPick([...selected]);
  });
  foot.appendChild(cancel);
  foot.appendChild(footLabel);
  foot.appendChild(add);
  updateFoot();

  box.appendChild(head);
  box.appendChild(search);
  box.appendChild(list);
  box.appendChild(foot);
  overlay.appendChild(box);

  const onKey = (e) => {
    if (e.key === "Escape") overlay.remove();
  };
  overlay.addEventListener("mousedown", (e) => {
    if (e.target === overlay) overlay.remove();
  });
  document.addEventListener("keydown", onKey, { once: true });

  document.body.appendChild(overlay);
  search.focus();
  filter();
}

class TrixUI {
  constructor(node) {
    this.node = node;
    this.isSimple = node.type === "TrixBypasserSimple";
    this._height = 100;

    this.el = document.createElement("div");
    this.el.className = "sergio-trix";

    this.header = document.createElement("div");
    this.header.className = "sergio-trix-header";
    this.list = document.createElement("div");
    this.list.className = "sergio-trix-list";

    this.modeBtn = makeButton("Mode: Bypass", "", () => {
      const state = this.state;
      state.muteMode = state.muteMode === "mute" ? "bypass" : "mute";
      this.updateHeader();
      this.commit(true);
    });

    this.addBtn = makeButton("＋ Add", "", () => {
      openPicker(this.node, (nodes) => {
        if (!nodes.length) return;
        const state = this.state;
        for (const n of nodes) {
          state.targets.push({ name: nodeLabel(n), value: String(n.id), active: true });
        }
        this.commit(true);
      });
    });

    this.el.appendChild(this.header);
    this.el.appendChild(this.list);
    this.buildHeader();
    this.render();

    const ro = new ResizeObserver(() => this.resize());
    ro.observe(this.el);
  }

  get state() {
    return this.node.properties && this.node.properties.trixBypasserState;
  }

  buildHeader() {
    this.header.replaceChildren();
    this.header.appendChild(this.addBtn);
    if (!this.isSimple) {
      this.header.appendChild(makeButton("＋ Group", "", () => {
        const groups = this.state.groups;
        const id = String.fromCharCode(65 + groups.length);
        groups.push({
          id, name: `Group ${id}`, active: true, collapsed: false,
          targets: [{ value: "", active: true }]
        });
        this.commit(true);
      }));
    }
    const spacer = document.createElement("div");
    spacer.style.flex = "1";
    this.header.appendChild(spacer);
    this.header.appendChild(this.modeBtn);
  }

  updateHeader() {
    this.modeBtn.textContent = `Mode: ${
      this.state && this.state.muteMode === "mute" ? "Mute" : "Bypass"}`;
  }

  targetRow(target) {
    const row = document.createElement("div");
    row.className = "sergio-trix-row";
    row.appendChild(makeSwitch(!!target.active, () => {
      target.active = !target.active;
      this.commit(true);
    }));
    const name = document.createElement("div");
    const ids = targetIds(target);
    const label = ids.map((id) => {
      const t = findNodeById(id);
      return t ? nodeLabel(t) : `id:${id}`;
    }).join(", ");
    name.className = "sergio-trix-name" + (label ? "" : " empty");
    name.textContent = label || "no target — pick nodes";
    name.title = target.value || "";
    row.appendChild(name);
    const eye = document.createElement("button");
    eye.className = "sergio-trix-ico";
    eye.textContent = "◉";
    eye.title = "Center viewport on target";
    eye.addEventListener("click", () => centerOnTarget(this.node));
    row.appendChild(eye);
    const del = document.createElement("button");
    del.className = "sergio-trix-ico del";
    del.textContent = "×";
    del.title = "Remove target";
    del.addEventListener("click", () => {
      if (this.isSimple) {
        const i = this.state.targets.indexOf(target);
        if (i >= 0) this.state.targets.splice(i, 1);
      } else {
        for (const g of this.state.groups) {
          const i = (g.targets || []).indexOf(target);
          if (i >= 0) { g.targets.splice(i, 1); break; }
        }
      }
      this.commit(true);
    });
    row.appendChild(del);
    return row;
  }

  groupRow(group) {
    const row = document.createElement("div");
    row.className = "sergio-trix-row";
    const arrow = document.createElement("div");
    arrow.className = "sergio-trix-arrow";
    arrow.textContent = group.collapsed ? "▸" : "▾";
    arrow.title = group.collapsed ? "Expand" : "Collapse";
    arrow.addEventListener("click", () => {
      group.collapsed = !group.collapsed;
      this.commit(true);
    });
    row.appendChild(arrow);
    const input = document.createElement("input");
    input.className = "sergio-trix-groupname";
    input.value = group.name;
    input.title = "Group name";
    input.addEventListener("input", () => { group.name = input.value; this.commit(false); });
    row.appendChild(input);
    row.appendChild(makeSwitch(!!group.active, () => {
      group.active = !group.active;
      this.commit(true);
    }));
    const add = document.createElement("button");
    add.className = "sergio-trix-ico";
    add.textContent = "＋";
    add.title = "Add target to group";
    add.addEventListener("click", () => {
      openPicker(this.node, (nodes) => {
        if (!nodes.length) return;
        for (const n of nodes) {
          group.targets.push({ name: nodeLabel(n), value: String(n.id), active: true });
        }
        this.commit(true);
      });
    });
    row.appendChild(add);
    const del = document.createElement("button");
    del.className = "sergio-trix-ico del";
    del.textContent = "×";
    del.title = "Remove group";
    del.addEventListener("click", () => {
      const i = this.state.groups.indexOf(group);
      if (i >= 0) this.state.groups.splice(i, 1);
      this.commit(true);
    });
    row.appendChild(del);
    return row;
  }

  render() {
    this.updateHeader();
    const state = this.state;
    this.list.replaceChildren();
    if (!state) return;
    if (this.isSimple) {
      const targets = state.targets || [];
      if (!targets.length) {
        const empty = document.createElement("div");
        empty.className = "sergio-trix-empty";
        empty.textContent = "No targets — press '+ Add' to pick nodes on the canvas.";
        this.list.appendChild(empty);
      } else {
        for (const t of targets) this.list.appendChild(this.targetRow(t));
      }
    } else {
      const groups = state.groups || [];
      if (!groups.length) {
        const empty = document.createElement("div");
        empty.className = "sergio-trix-empty";
        empty.textContent = "No groups — press '+ Group' to start.";
        this.list.appendChild(empty);
      } else {
        for (const g of groups) {
          this.list.appendChild(this.groupRow(g));
          if (g.collapsed) continue;
          if (!(g.targets || []).length) {
            const empty = document.createElement("div");
            empty.className = "sergio-trix-empty";
            empty.textContent = "Empty group — press '＋' on the group to add nodes.";
            this.list.appendChild(empty);
          } else {
            for (const t of g.targets) {
              const row = this.targetRow(t);
              row.classList.add("groups");
              this.list.appendChild(row);
            }
          }
        }
      }
    }
    this.resize();
  }

  commit(render) {
    trixEnforce(this.node);
    if (render) this.render();
    if (this.node.setDirtyCanvas) this.node.setDirtyCanvas(true, true);
  }

  resize() {
    const headerH = this.header.offsetHeight || 28;
    const listH = this.list.scrollHeight || 30;
    const h = Math.min(380, Math.max(70, headerH + listH + 6));
    if (Math.abs(h - this._height) < 2) return;
    this._height = h;
    const w = Math.max(this.node.size ? this.node.size[0] : 0, 300);
    if (this.node.setSize) this.node.setSize([w, h]);
  }
}

function attachWidget(node, ui) {
  node.widgets = node.widgets || [];
  let widget = node.widgets.find((wd) => wd.name === "sergio_trix");
  if (!widget) {
    widget = node.addDOMWidget("sergio_trix", "SERGIO_TRIX", ui.el, {
      serialize: false,
      hideOnZoom: false,
      getMinHeight: () => ui._height,
      getMaxHeight: () => ui._height,
      getHeight: () => ui._height
    });
  } else {
    widget.element = ui.el;
  }
  const origCompute = node.computeSize.bind(node);
  node.computeSize = function (...args) {
    const sz = origCompute(...args) || [320, 100];
    if (ui._height > (sz[1] || 0)) sz[1] = ui._height;
    return sz;
  };
  return widget;
}

function trixInit(node) {
  if (!node.properties) node.properties = {};
  const state = node.properties.trixBypasserState;
  if (!state) node.properties.trixBypasserState = defaultState(node.type === "TrixBypasserSimple");
  if (!node.properties.trixBypasserOriginalModes) node.properties.trixBypasserOriginalModes = {};

  if (node.trixUi) {
    node.trixUi.render();
    trixEnforce(node);
    return;
  }

  const ui = new TrixUI(node);
  node.trixUi = ui;
  attachWidget(node, ui);
  trixEnforce(node);
}

function trixSyncAll() {
  const nodes = (app.graph?._nodes || []).filter((n) => NODE_TYPES.includes(n.type));
  for (const n of nodes) trixInit(n);
}

injectCss();

app.registerExtension({
  name: "SergioNodes.TrixBypasser",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_TYPES.includes(nodeData.name)) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const r = onCreated ? onCreated.apply(this, args) : undefined;
      trixInit(this);
      return r;
    };

    const onRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function (...args) {
      restoreAll(this);
      return onRemoved ? onRemoved.apply(this, args) : undefined;
    };
  },
  async afterConfigureGraph() {
    trixSyncAll();
  }
});