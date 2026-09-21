const UPSTREAM = null; // nodo original de SergioNodes (extensión frontend sin upstream)

import { app } from "../../scripts/app.js";

/** Adds a "Node ID" entry to every node's right-click context menu, in both the
 *  classic LiteGraph menu and the Vue (Nodes 2.0) menu, using the official
 *  getNodeMenuItems extension hook. Clicking the entry copies the id so it can
 *  be pasted into ID-based nodes such as the Trix Bypassers. */

function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.focus();
  area.select();
  try {
    document.execCommand("copy");
  } catch (e) {
    console.error("Failed to copy node id:", e);
  }
  document.body.removeChild(area);
}

app.registerExtension({
  name: "SergioNodes.NodeIDContextMenu",
  getNodeMenuItems(node) {
    return [
      null,
      {
        content: `Node ID: ${node.id}`,
        title: "Copy node id to clipboard",
        callback: () => copyText(String(node.id))
      }
    ];
  }
});