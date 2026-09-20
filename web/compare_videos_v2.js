import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/** SergioNodes Compare Videos v2 — in-node A/B slider widget.
 *
 *  The backend returns a ui payload with two temp videos
 *  ({ a_video: [SavedResult], b_video: [SavedResult] }); this extension
 *  renders them as two overlaid <video> elements with a draggable divider,
 *  like the stock Compare Images (ImageCompare) node but for videos. */

const NODE_TYPE = "CompareVideosV2";

const CV2_CSS = `
.sergio-cv2 { position:relative; width:100%; overflow:hidden; user-select:none;
  background:#000; border-radius:6px; }
.sergio-cv2 video.sergio-cv2-layer { position:absolute; inset:0; width:100%;
  height:100%; object-fit:contain; pointer-events:none; }
.sergio-cv2 video.sergio-cv2-layer.master { pointer-events:auto; }
.sergio-cv2 video.sergio-cv2-layer.a { z-index:2; }
.sergio-cv2 .sergio-cv2-divider { position:absolute; top:0; bottom:0; width:22px;
  margin-left:-11px; z-index:3; cursor:ew-resize; touch-action:none; }
.sergio-cv2 .sergio-cv2-divider .line { position:absolute; top:0; bottom:0;
  left:50%; width:2px; margin-left:-1px; background:rgba(255,255,255,.85);
  box-shadow:0 0 4px rgba(0,0,0,.8); }
.sergio-cv2 .sergio-cv2-divider .knob { position:absolute; top:50%; left:50%;
  margin:-11px 0 0 -11px; width:22px; height:22px; border-radius:50%;
  background:#fff; box-shadow:0 0 6px rgba(0,0,0,.6); display:flex;
  align-items:center; justify-content:center; font-size:10px; color:#333;
  font-weight:bold; }
.sergio-cv2 .sergio-cv2-tag { position:absolute; top:6px; z-index:4; font-size:11px;
  color:#fff; background:rgba(0,0,0,.55); border-radius:4px; padding:1px 7px; }
.sergio-cv2 .sergio-cv2-tag.a { left:6px; }
.sergio-cv2 .sergio-cv2-tag.b { right:6px; }
.sergio-cv2 .sergio-cv2-hint { position:absolute; inset:0; z-index:5;
  display:flex; align-items:center; justify-content:center; color:#9a9aa6;
  font-size:12px; background:rgba(10,10,12,.6); }
`;

function injectCss() {
  if (document.getElementById("sergio-cv2-css")) return;
  const style = document.createElement("style");
  style.id = "sergio-cv2-css";
  style.textContent = CV2_CSS;
  document.head.appendChild(style);
}

function toViewUrl(item, bust) {
  if (!item) return null;
  const p = new URLSearchParams({
    filename: item.filename || item.name || "",
    subfolder: item.subfolder || "",
    type: item.type || "temp"
  });
  if (bust) p.set("rand", String(Date.now()));
  return api.apiURL(`/view?${p}`);
}

class CV2UI {
  constructor(node) {
    this.node = node;
    this._p = 0.5;
    this._aspect = 16 / 9;
    this._height = 180;

    this.el = document.createElement("div");
    this.el.className = "sergio-cv2";
    this.el.style.height = this._height + "px";

    this.videos = { a: this.makeVideo("a", false), b: this.makeVideo("b", true) };
    const b = this.videos.b;
    b.classList.add("master");

    this.divider = document.createElement("div");
    this.divider.className = "sergio-cv2-divider";
    this.divider.innerHTML = '<div class="line"></div><div class="knob">⇔</div>';

    this.hint = document.createElement("div");
    this.hint.className = "sergio-cv2-hint";
    this.hint.textContent = "Run the node to load the videos…";

    this.tagA = this.tag("a", "A");
    this.tagB = this.tag("b", "B");

    this.el.appendChild(this.videos.b);
    this.el.appendChild(this.videos.a);
    this.el.appendChild(this.divider);
    this.el.appendChild(this.tagA);
    this.el.appendChild(this.tagB);
    this.el.appendChild(this.hint);

    this.bindSync(this.videos.a, this.videos.b);
    this.bindDrag();

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(this.el);
  }

  makeVideo(which, controls) {
    const v = document.createElement("video");
    v.className = "sergio-cv2-layer " + which;
    v.muted = true;
    v.loop = true;
    v.playsInline = true;
    v.setAttribute("playsinline", "");
    if (controls) v.controls = true;
    v.addEventListener("loadedmetadata", () => {
      if (v.videoWidth > 0 && v.videoHeight > 0) {
        this._aspect = v.videoWidth / v.videoHeight;
        this.resize();
      }
    });
    return v;
  }

  tag(which, text) {
    const t = document.createElement("div");
    t.className = "sergio-cv2-tag " + which;
    t.textContent = text;
    return t;
  }

  bindSync(slave, master) {
    const snap = () => {
      if (Math.abs(slave.currentTime - master.currentTime) > 0.05) {
        slave.currentTime = master.currentTime;
      }
    };
    master.addEventListener("play", () => { slave.currentTime = master.currentTime; slave.play().catch(() => {}); });
    master.addEventListener("pause", () => slave.pause());
    master.addEventListener("seeked", snap);
    master.addEventListener("timeupdate", snap);
    master.addEventListener("ended", () => { slave.pause(); });
  }

  bindDrag() {
    const divider = this.divider;
    const el = this.el;
    divider.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      try {
        divider.setPointerCapture(e.pointerId);
      } catch (err) { /* older browsers: fall back to window listeners */ }

      const update = (ev) => {
        const rect = el.getBoundingClientRect();
        if (!rect.width) return;
        const p = Math.min(0.97, Math.max(0.03, (ev.clientX - rect.left) / rect.width));
        this.set(p);
      };
      const release = () => {
        if (divider.hasPointerCapture && divider.hasPointerCapture(e.pointerId)) {
          try { divider.releasePointerCapture(e.pointerId); } catch (err) {}
        }
        divider.removeEventListener("pointermove", update);
        divider.removeEventListener("pointerup", release);
        divider.removeEventListener("pointercancel", release);
      };
      divider.addEventListener("pointermove", update);
      divider.addEventListener("pointerup", release);
      divider.addEventListener("pointercancel", release);
    });
  }

  set(p) {
    this._p = p;
    const a = this.videos.a;
    const right = 100 * (1 - p);
    a.style.clipPath = `inset(0 ${right}% 0 0)`;
    this.divider.style.left = (100 * p) + "%";
  }

  loadResult(msg) {
    const data = msg || {};
    const aList = data.a_video || [];
    const bList = data.b_video || [];
    const aFile = aList.length ? aList[0] : (data.a_video || null);
    const bFile = bList.length ? bList[0] : (data.b_video || null);

    this.hint.style.display = "none";
    const both = !!(aFile && bFile);
    this.divider.style.display = both ? "" : "none";
    this.tagA.style.display = aFile ? "" : "none";
    this.tagB.style.display = bFile ? "" : "none";

    if (aFile && bFile) {
      const urlA = toViewUrl(aFile, true);
      const urlB = toViewUrl(bFile, true);
      this.videos.a.src = urlA;
      this.videos.b.src = urlB;
      this.videos.a.autoplay = true;
      this.videos.b.autoplay = true;
      this.videos.a.muted = true;
      this.videos.b.muted = true;
      this.set(this._p);
      this.playAll();
    } else if (aFile && !bFile) {
      this.videos.a.src = toViewUrl(aFile, true);
      this.videos.a.muted = false;
      this.videos.a.autoplay = true;
      this.videos.b.removeAttribute("src");
      this.playAll();
    } else if (bFile && !aFile) {
      this.videos.b.src = toViewUrl(bFile, true);
      this.videos.b.muted = false;
      this.videos.b.autoplay = true;
      this.videos.a.removeAttribute("src");
      this.playAll();
    } else {
      this.hint.style.display = "flex";
    }
  }

  playAll() {
    for (const key of ["a", "b"]) {
      const v = this.videos[key];
      if (v.src) v.play().catch(() => {});
    }
  }

  resize() {
    const w = this.el.clientWidth || 300;
    const h = Math.min(480, Math.max(120, Math.round(w / this._aspect)));
    if (Math.abs(h - this._height) < 3) return;
    this._height = h;
    this.el.style.height = h + "px";
    const sz = this.node.size ? this.node.size : [0, 0];
    if (Math.abs((sz[1] || 0) - h) > 2 && this.node.setSize) {
      this.node.setSize([Math.max(sz[0] || 0, 300), h]);
    }
  }
}

function attachWidget(node, ui) {
  node.widgets = node.widgets || [];
  let widget = node.widgets.find((wd) => wd.name === "sergio_cv2");
  if (!widget) {
    widget = node.addDOMWidget("sergio_cv2", "SERGIO_CV2", ui.el, {
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
    const sz = origCompute(...args) || [360, 180];
    if (ui._height > (sz[1] || 0)) sz[1] = ui._height;
    return sz;
  };
  return widget;
}

function cv2Init(node) {
  if (node.cv2Ui) {
    node.cv2Ui.resize();
    return;
  }
  const ui = new CV2UI(node);
  node.cv2Ui = ui;
  attachWidget(node, ui);

  const origExec = node.onExecuted;
  node.onExecuted = function (msg) {
    if (origExec) origExec.call(this, msg);
    ui.loadResult(msg);
  };
}

function cv2SyncAll() {
  const nodes = (app.graph?._nodes || []).filter((n) => n.type === NODE_TYPE);
  for (const n of nodes) cv2Init(n);
}

injectCss();

app.registerExtension({
  name: "SergioNodes.CompareVideosV2",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE_TYPE) return;

    const onCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (...args) {
      const r = onCreated ? onCreated.apply(this, args) : undefined;
      cv2Init(this);
      return r;
    };
  },
  async afterConfigureGraph() {
    cv2SyncAll();
  }
});