const UPSTREAM = ["Academia SD Resolution Calc", "https://github.com/AcademiaSD/comfyui_AcademiaSD", "AcademiaSD_ResolutionCalc"];

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

function getInputOriginNode(node, input) {
    if (typeof node.getInputNode === "function") {
        return node.getInputNode(node.inputs.indexOf(input)) || null;
    }
    if (node.graph && node.graph._links && typeof node.graph._links.get === "function") {
        const link = node.graph._links.get(input.link);
        return link ? node.graph.getNodeById(link.origin_id) : null;
    }
    if (node.graph && Array.isArray(node.graph.links)) {
        const link = node.graph.links.find((l) => l.id === input.link);
        return link ? node.graph.getNodeById(link.origin_id) : null;
    }
    return null;
}

function getConnectedImageNode(node) {
    if (!node.graph) return null;
    const input = (node.inputs || []).find((i) => i.name === "image");
    if (!input || input.link == null) return null;
    return getInputOriginNode(node, input);
}

function getImageRef(img) {
    if (!img) return null;
    if (typeof img === "string") {
        const annotated = img.match(/^(.*?)(?:\s+\[(input|output|temp)\])?$/);
        return { filename: annotated?.[1] || img, subfolder: "", type: annotated[2] || "input" };
    }
    if (img.filename) {
        return {
            filename: img.filename,
            subfolder: img.subfolder || "",
            type: img.type || "input",
        };
    }
    return null;
}

function getImageRefFromNode(sourceNode) {
    const seen = new Set();
    let node = sourceNode;
    while (node && !seen.has(node)) {
        seen.add(node);
        if (Array.isArray(node.images) && node.images.length > 0) {
            const ref = getImageRef(node.images[0]);
            if (ref) return ref;
        }
        const widget = (node.widgets || []).find((w) => w.name === "image");
        const ref = getImageRef(widget && widget.value);
        if (ref) return ref;
        const imgInput = (node.inputs || []).find(
            (i) => i.link != null && (!i.type || i.type === "IMAGE")
        );
        const input = imgInput || (node.inputs || []).find((i) => i.link != null);
        if (!input) return null;
        node = getInputOriginNode(node, input);
    }
    return null;
}

function pyRound(x) {
    const lower = Math.floor(x);
    const diff = x - lower;
    if (diff < 0.5) return lower;
    if (diff > 0.5) return lower + 1;
    return lower % 2 === 0 ? lower : lower + 1;
}

function calcResolution(node) {
    const get = (name, fallback) => {
        const w = (node.widgets || []).find((widget) => widget.name === name);
        return w ? w.value : fallback;
    };
    const megapixel = Number(get("megapixel", 1.0));
    const divisibleBy = Number(get("divisible_by", "16"));
    const customRatio = Boolean(get("custom_ratio", false));
    const ratioRaw = String(get("aspect_ratio", "1:1 (Perfect Square)")).trim();
    const dropdownIsCustom = ratioRaw.startsWith("Custom");
    // El ratio manual se usa si el interruptor lo pide o si el desplegable esta
    // en "Custom": mismas dos caras del mismo ajuste que en el backend.
    const ratioStr = customRatio || dropdownIsCustom
        ? String(get("custom_aspect_ratio", "1:1"))
        : ratioRaw.split(" ")[0];
    const cleaned = ratioStr.trim().replaceAll("/", ":");
    const parts = cleaned.split(":").map(Number);
    if (!parts[0] || !parts[1]) return null;
    const ratio = parts[0] / parts[1];
    const targetArea = megapixel * 1048576;
    const hExact = Math.sqrt(targetArea / ratio);
    const wExact = hExact * ratio;
    const width = Math.max(divisibleBy, pyRound(wExact / divisibleBy) * divisibleBy);
    const height = Math.max(divisibleBy, pyRound(hExact / divisibleBy) * divisibleBy);
    return `${width} × ${height}`;
}

app.registerExtension({
    name: "SergioNodes.ResolutionSelector",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "Resolution_Selector") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            onNodeCreated?.apply(this, arguments);

            let resultWidget = null;
            try {
                resultWidget = ComfyWidgets["STRING"](this, "result", ["STRING", { multiline: false }], app).widget;
                resultWidget.inputEl.readOnly = true;
                resultWidget.inputEl.style.color = "#00ff88";
                resultWidget.inputEl.style.fontWeight = "bold";
                resultWidget.inputEl.style.fontFamily = "monospace";
                resultWidget.inputEl.style.textAlign = "center";
                resultWidget.serializeValue = () => "";
            } catch (e) {
                console.warn("[SergioNodes] No se pudo crear el visor de resolución:", e);
            }

            const setResult = (node, text) => {
                if (!resultWidget) return;
                resultWidget.value = text;
                app.graph.setDirtyCanvas(true, true);
            };
            const refresh = () => {
                setResult(this, calcResolution(this) ?? "ratio no válido");
            };

            for (const name of [
                "megapixel",
                "aspect_ratio",
                "divisible_by",
                "custom_ratio",
                "custom_aspect_ratio",
            ]) {
                const widget = this.widgets.find((w) => w.name === name);
                if (!widget) continue;
                const original = widget.callback;
                widget.callback = (...args) => {
                    original?.apply(widget, args);
                    refresh();
                };
            }

            this.addWidget("button", "Usar tamaño de imagen", "", () => {
                const sourceNode = getConnectedImageNode(this);
                if (!sourceNode) {
                    alert("Conecta una imagen al nodo antes de usar este botón.");
                    return;
                }
                const ref = getImageRefFromNode(sourceNode);
                if (!ref) {
                    alert("No se pudo obtener el archivo de la imagen conectada.");
                    return;
                }
                // El backend resuelve [input]/[output]/[temp] internamente.
                const params = new URLSearchParams({
                    filename: `${ref.filename} [${ref.type}]`,
                });
                api.fetchApi(`/academia_res/get_image_size?${params}`)
                    .then((r) => r.json())
                    .then((data) => {
                        if (data.error) {
                            alert("Error al leer la imagen: " + data.error);
                            return;
                        }
                        const ratioWidget = this.widgets.find((w) => w.name === "custom_ratio");
                        const valueWidget = this.widgets.find((w) => w.name === "custom_aspect_ratio");
                        if (ratioWidget) ratioWidget.value = true;
                        if (valueWidget) valueWidget.value = `${data.width}:${data.height}`;
                        refresh();
                    })
                    .catch((err) => alert("Error consultando el tamaño de imagen: " + err));
            }, { serialize: false });

            // El backend manda el tamano REAL de la imagen conectada (aunque
            // venga de un VAE Decode, upscaler o batch, no de un fichero).
            this._academiaRescalcHandler = (event) => {
                const data = event.detail;
                if (String(data.node_id) !== String(this.id)) return;
                setResult(this, `${data.width} × ${data.height}`);
            };
            api.addEventListener("academia.rescalc.image_size", this._academiaRescalcHandler);

            setTimeout(refresh, 50);
        };

        const onNodeRemoved = nodeType.prototype.onNodeRemoved;
        nodeType.prototype.onNodeRemoved = function () {
            if (this._academiaRescalcHandler) {
                api.removeEventListener("academia.rescalc.image_size", this._academiaRescalcHandler);
                this._academiaRescalcHandler = null;
            }
            onNodeRemoved?.apply(this, arguments);
        };
    },
});