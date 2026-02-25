/**
 * Renderer Module for Local LLM Chat Interface.
 *
 * Converts message content to styled HTML with Markdown parsing,
 * XSS sanitization, lazy-loaded images, link hover previews,
 * syntax highlighting for code blocks, LaTeX math rendering,
 * and Mermaid diagram rendering.
 *
 * Uses Marked.js with GitHub Flavored Markdown support.
 * Uses Highlight.js for syntax highlighting with auto-detection.
 * Uses KaTeX for LaTeX math expression rendering.
 * Uses Mermaid.js for diagram rendering.
 *
 * Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7
 */

// ---------------------------------------------------------------------------
// Lazy-loaded library instances
// ---------------------------------------------------------------------------

let marked = null;
let markedInitialized = false;
let hljs = null;
let hljsInitialized = false;
let katex = null;
let katexInitialized = false;
let mermaid = null;
let mermaidInitialized = false;

/** Counter for unique code block IDs (used by copy buttons) */
let codeBlockCounter = 0;

/**
 * Lazily load and configure Highlight.js.
 * Returns the hljs instance.
 * @returns {Promise<Object|null>} Highlight.js instance or null on failure
 */
async function getHljs() {
  if (hljsInitialized && hljs) return hljs;

  try {
    const mod =
      await import("https://cdn.jsdelivr.net/gh/nicolo-ribaudo/tc39-proposal-await-import@main/highlight.min.mjs").catch(
        () => null,
      );

    // Fallback: try loading via script tag if ESM import fails
    if (!mod) {
      hljs = await loadHljsViaScript();
    } else {
      hljs = mod.default || mod;
    }

    if (hljs) {
      hljsInitialized = true;
      // Inject Highlight.js theme stylesheet if not already present
      injectHljsTheme();
    }

    return hljs;
  } catch (err) {
    console.warn(
      "Failed to load Highlight.js via ESM, trying script tag:",
      err,
    );
    try {
      hljs = await loadHljsViaScript();
      if (hljs) {
        hljsInitialized = true;
        injectHljsTheme();
      }
      return hljs;
    } catch (err2) {
      console.error("Failed to load Highlight.js:", err2);
      return null;
    }
  }
}

/**
 * Load Highlight.js via a <script> tag as fallback.
 * @returns {Promise<Object|null>}
 */
function loadHljsViaScript() {
  return new Promise((resolve) => {
    if (window.hljs) {
      resolve(window.hljs);
      return;
    }
    const script = document.createElement("script");
    script.src =
      "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/highlight.min.js";
    script.onload = () => resolve(window.hljs || null);
    script.onerror = () => resolve(null);
    document.head.appendChild(script);
  });
}

/**
 * Inject the Highlight.js dark theme stylesheet if not already present.
 */
function injectHljsTheme() {
  const THEME_ID = "hljs-theme-link";
  if (document.getElementById(THEME_ID)) return;

  const link = document.createElement("link");
  link.id = THEME_ID;
  link.rel = "stylesheet";
  link.href =
    "https://cdn.jsdelivr.net/npm/@highlightjs/cdn-assets@11.9.0/styles/github-dark.min.css";
  document.head.appendChild(link);
}

// ---------------------------------------------------------------------------
// KaTeX lazy loading (Requirement 16.5)
// ---------------------------------------------------------------------------

/**
 * Lazily load KaTeX for math expression rendering.
 * Loads both the JS library and CSS stylesheet.
 * @returns {Promise<Object|null>} KaTeX instance or null on failure
 */
async function getKatex() {
  if (katexInitialized && katex) return katex;

  try {
    // Try ESM import first
    const mod =
      await import("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.mjs").catch(
        () => null,
      );

    if (mod) {
      katex = mod.default || mod;
    } else {
      // Fallback: load via script tag
      katex = await loadKatexViaScript();
    }

    if (katex) {
      katexInitialized = true;
      injectKatexStyles();
    }

    return katex;
  } catch (err) {
    console.warn("Failed to load KaTeX via ESM, trying script tag:", err);
    try {
      katex = await loadKatexViaScript();
      if (katex) {
        katexInitialized = true;
        injectKatexStyles();
      }
      return katex;
    } catch (err2) {
      console.error("Failed to load KaTeX:", err2);
      return null;
    }
  }
}

/**
 * Load KaTeX via a <script> tag as fallback.
 * @returns {Promise<Object|null>}
 */
function loadKatexViaScript() {
  return new Promise((resolve) => {
    if (window.katex) {
      resolve(window.katex);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js";
    script.onload = () => resolve(window.katex || null);
    script.onerror = () => resolve(null);
    document.head.appendChild(script);
  });
}

/**
 * Inject the KaTeX CSS stylesheet if not already present.
 */
function injectKatexStyles() {
  const STYLE_ID = "katex-style-link";
  if (document.getElementById(STYLE_ID)) return;

  const link = document.createElement("link");
  link.id = STYLE_ID;
  link.rel = "stylesheet";
  link.href = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css";
  document.head.appendChild(link);
}

// ---------------------------------------------------------------------------
// Mermaid.js lazy loading (Requirement 16.6)
// ---------------------------------------------------------------------------

/**
 * Lazily load and configure Mermaid.js for diagram rendering.
 * @returns {Promise<Object|null>} Mermaid instance or null on failure
 */
async function getMermaid() {
  if (mermaidInitialized && mermaid) return mermaid;

  try {
    const mod =
      await import("https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.esm.min.mjs").catch(
        () => null,
      );

    if (mod) {
      mermaid = mod.default || mod;
    } else {
      mermaid = await loadMermaidViaScript();
    }

    if (mermaid) {
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "strict",
        fontFamily: '"Inter", sans-serif',
      });
      mermaidInitialized = true;
    }

    return mermaid;
  } catch (err) {
    console.warn("Failed to load Mermaid.js via ESM, trying script tag:", err);
    try {
      mermaid = await loadMermaidViaScript();
      if (mermaid) {
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "strict",
          fontFamily: '"Inter", sans-serif',
        });
        mermaidInitialized = true;
      }
      return mermaid;
    } catch (err2) {
      console.error("Failed to load Mermaid.js:", err2);
      return null;
    }
  }
}

/**
 * Load Mermaid.js via a <script> tag as fallback.
 * @returns {Promise<Object|null>}
 */
function loadMermaidViaScript() {
  return new Promise((resolve) => {
    if (window.mermaid) {
      resolve(window.mermaid);
      return;
    }
    const script = document.createElement("script");
    script.src =
      "https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js";
    script.onload = () => resolve(window.mermaid || null);
    script.onerror = () => resolve(null);
    document.head.appendChild(script);
  });
}

/** Counter for unique mermaid diagram IDs */
let mermaidCounter = 0;

/**
 * Lazily load and configure Marked.js.
 * Returns the configured `marked` instance.
 * @returns {Promise<Object>} Marked module
 */
async function getMarked() {
  if (markedInitialized && marked) return marked;

  try {
    const mod =
      await import("https://cdn.jsdelivr.net/npm/marked@12.0.2/lib/marked.esm.js");
    marked = mod;

    // Configure Marked with GFM support
    marked.marked.setOptions({
      gfm: true, // GitHub Flavored Markdown
      breaks: true, // Convert \n to <br>
      pedantic: false,
    });

    // Install custom renderer overrides (includes code block handling)
    marked.marked.use({ renderer: buildCustomRenderer() });

    markedInitialized = true;
    return marked;
  } catch (err) {
    console.error("Failed to load Marked.js:", err);
    return null;
  }
}

// ---------------------------------------------------------------------------
// XSS Sanitization
// ---------------------------------------------------------------------------

/** Allowed HTML tags after Markdown rendering */
const ALLOWED_TAGS = new Set([
  "p",
  "br",
  "strong",
  "em",
  "del",
  "s",
  "b",
  "i",
  "u",
  "code",
  "pre",
  "blockquote",
  "ul",
  "ol",
  "li",
  "a",
  "img",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "table",
  "thead",
  "tbody",
  "tr",
  "th",
  "td",
  "hr",
  "span",
  "div",
  "input",
  "label",
  "sup",
  "sub",
  "button",
  // SVG elements for Mermaid diagrams (Requirement 16.6)
  "svg",
  "g",
  "path",
  "rect",
  "circle",
  "ellipse",
  "line",
  "polyline",
  "polygon",
  "text",
  "tspan",
  "defs",
  "clippath",
  "marker",
  "foreignobject",
  "style",
]);

/** Allowed attributes per tag */
const ALLOWED_ATTRS = {
  a: ["href", "title", "target", "rel", "class", "data-url"],
  img: ["src", "alt", "title", "loading", "width", "height", "class"],
  input: ["type", "checked", "disabled"],
  td: ["align"],
  th: ["align"],
  code: ["class"],
  pre: ["class", "data-lang"],
  span: ["class", "style", "aria-hidden"],
  div: ["class", "data-code-block-id", "data-mermaid-id"],
  label: ["class"],
  button: ["class", "type", "data-code-block-id", "aria-label", "title"],
  // SVG attributes for Mermaid diagrams
  svg: [
    "class",
    "viewbox",
    "width",
    "height",
    "xmlns",
    "role",
    "aria-roledescription",
    "style",
    "id",
  ],
  g: ["class", "transform", "id", "clip-path"],
  path: [
    "d",
    "class",
    "fill",
    "stroke",
    "stroke-width",
    "style",
    "id",
    "marker-end",
  ],
  rect: [
    "x",
    "y",
    "width",
    "height",
    "rx",
    "ry",
    "class",
    "fill",
    "stroke",
    "style",
    "id",
  ],
  circle: ["cx", "cy", "r", "class", "fill", "stroke", "style"],
  ellipse: ["cx", "cy", "rx", "ry", "class", "fill", "stroke", "style"],
  line: ["x1", "y1", "x2", "y2", "class", "stroke", "stroke-width", "style"],
  polyline: ["points", "class", "fill", "stroke", "style"],
  polygon: ["points", "class", "fill", "stroke", "style"],
  text: [
    "x",
    "y",
    "class",
    "style",
    "dominant-baseline",
    "text-anchor",
    "dy",
    "dx",
    "fill",
  ],
  tspan: ["x", "y", "class", "dy", "dx"],
  defs: [],
  clippath: ["id"],
  marker: [
    "id",
    "viewbox",
    "refx",
    "refy",
    "markerwidth",
    "markerheight",
    "orient",
  ],
  foreignobject: ["x", "y", "width", "height", "class"],
  style: [],
  "*": ["class"],
};

/** Dangerous URL schemes */
const DANGEROUS_SCHEMES = /^\s*(javascript|vbscript|data):/i;

/**
 * Sanitize rendered HTML to prevent XSS.
 * Uses a DOM-based allowlist approach.
 *
 * @param {string} html - Raw HTML string
 * @returns {string} Sanitized HTML
 */
export function sanitizeHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  sanitizeNode(doc.body);
  return doc.body.innerHTML;
}

/**
 * Recursively sanitize a DOM node tree.
 * @param {Node} node - DOM node to sanitize
 */
function sanitizeNode(node) {
  const children = Array.from(node.childNodes);

  for (const child of children) {
    if (child.nodeType === Node.TEXT_NODE) continue;

    if (child.nodeType === Node.COMMENT_NODE) {
      child.remove();
      continue;
    }

    if (child.nodeType !== Node.ELEMENT_NODE) {
      child.remove();
      continue;
    }

    const tag = child.tagName.toLowerCase();

    // Remove disallowed tags but keep their text content
    if (!ALLOWED_TAGS.has(tag)) {
      const text = document.createTextNode(child.textContent);
      child.replaceWith(text);
      continue;
    }

    // Strip disallowed attributes
    const allowedForTag = [
      ...(ALLOWED_ATTRS[tag] || []),
      ...(ALLOWED_ATTRS["*"] || []),
    ];
    const attrs = Array.from(child.attributes);
    for (const attr of attrs) {
      if (!allowedForTag.includes(attr.name)) {
        child.removeAttribute(attr.name);
      }
    }

    // Sanitize href / src values
    if (child.hasAttribute("href")) {
      const href = child.getAttribute("href");
      if (DANGEROUS_SCHEMES.test(href)) {
        child.removeAttribute("href");
        child.setAttribute("title", "[link removed for security]");
      }
    }
    if (child.hasAttribute("src")) {
      const src = child.getAttribute("src");
      if (DANGEROUS_SCHEMES.test(src)) {
        child.removeAttribute("src");
        child.setAttribute("alt", "[image removed for security]");
      }
    }

    // Remove event handler attributes (on*)
    const allAttrs = Array.from(child.attributes);
    for (const attr of allAttrs) {
      if (attr.name.startsWith("on")) {
        child.removeAttribute(attr.name);
      }
    }

    // Recurse into children
    sanitizeNode(child);
  }
}

// ---------------------------------------------------------------------------
// Custom Marked Renderer (images, links, task lists)
// ---------------------------------------------------------------------------

/**
 * Build a custom Marked renderer with:
 * - Lazy-loaded images with alt text
 * - Links that open in new tabs with hover preview data attributes
 * - GFM task list checkbox rendering
 *
 * @returns {Object} Marked renderer overrides
 */
function buildCustomRenderer() {
  return {
    /**
     * Render fenced code blocks with syntax highlighting and copy button.
     * Requirements: 16.2, 16.3, 16.4, 16.6
     *
     * - Integrates Highlight.js for syntax highlighting
     * - Supports manual language override via ```language
     * - Falls back to auto-detection when no language specified
     * - Adds a copy-to-clipboard button on each code block
     * - Renders Mermaid diagrams when language is "mermaid"
     */
    code(token) {
      const raw = token.text || "";
      const lang = (token.lang || "").trim().toLowerCase();

      // Handle Mermaid diagram blocks (Requirement 16.6)
      if (lang === "mermaid") {
        const diagramId = `mermaid-diagram-${++mermaidCounter}`;
        const escapedCode = escapeHtml(raw);
        return (
          `<div class="mermaid-wrapper" data-mermaid-id="${diagramId}">` +
          `<div class="mermaid-diagram" id="${diagramId}">${escapedCode}</div>` +
          `</div>`
        );
      }

      const blockId = `code-block-${++codeBlockCounter}`;

      let highlighted = escapeHtml(raw);
      let detectedLang = lang;

      if (hljs) {
        try {
          if (lang && hljs.getLanguage(lang)) {
            // Manual language override
            const result = hljs.highlight(raw, {
              language: lang,
              ignoreIllegals: true,
            });
            highlighted = result.value;
            detectedLang = lang;
          } else if (lang) {
            // Language specified but not recognized – try auto-detect
            const result = hljs.highlightAuto(raw);
            highlighted = result.value;
            detectedLang = result.language || lang;
          } else {
            // No language specified – auto-detect
            const result = hljs.highlightAuto(raw);
            highlighted = result.value;
            detectedLang = result.language || "";
          }
        } catch {
          // Highlighting failed – use escaped text
          highlighted = escapeHtml(raw);
        }
      }

      const langLabel = detectedLang ? escapeAttr(detectedLang) : "text";
      const langClass = detectedLang
        ? ` class="hljs language-${escapeAttr(detectedLang)}"`
        : ' class="hljs"';

      return (
        `<div class="code-block-wrapper" data-code-block-id="${blockId}">` +
        `<div class="code-block-header">` +
        `<span class="code-block-lang">${langLabel}</span>` +
        `<button type="button" class="code-copy-btn" data-code-block-id="${blockId}" aria-label="Copy code" title="Copy code">` +
        `<span class="code-copy-icon" aria-hidden="true">📋</span>` +
        `<span class="code-copy-label">Copy</span>` +
        `</button>` +
        `</div>` +
        `<pre data-lang="${langLabel}"><code${langClass}>${highlighted}</code></pre>` +
        `</div>`
      );
    },

    /**
     * Render images with lazy loading.
     * Requirement 16.7: image rendering with alt text support
     */
    image(token) {
      const href = escapeAttr(token.href || "");
      const alt = escapeAttr(token.text || "");
      const title = token.title ? ` title="${escapeAttr(token.title)}"` : "";
      return `<img src="${href}" alt="${alt}"${title} loading="lazy" class="rendered-image" />`;
    },

    /**
     * Render links with target=_blank and hover preview data attribute.
     * Requirement 16.8: link preview cards for external links
     */
    link(token) {
      const href = escapeAttr(token.href || "");
      const title = token.title ? ` title="${escapeAttr(token.title)}"` : "";
      const text = token.tokens
        ? this.parser.parseInline(token.tokens)
        : escapeHtml(token.text || href);

      // Detect external links
      const isExternal =
        href.startsWith("http://") || href.startsWith("https://");
      const target = isExternal
        ? ' target="_blank" rel="noopener noreferrer"'
        : "";
      const previewAttr = isExternal ? ` data-url="${href}"` : "";

      return `<a href="${href}"${title}${target}${previewAttr} class="rendered-link">${text}</a>`;
    },

    /**
     * Render list items with GFM task list checkbox support.
     * Requirement 16.1: task lists
     */
    listitem(token) {
      let body = this.parser.parse(token.tokens, !!token.loose);

      if (token.task) {
        const checked = token.checked ? " checked" : "";
        body = `<label class="task-list-label"><input type="checkbox"${checked} disabled class="task-list-checkbox" />${body}</label>`;
      }

      return `<li>${body}</li>\n`;
    },
  };
}

// ---------------------------------------------------------------------------
// Link Hover Preview
// ---------------------------------------------------------------------------

/** Tooltip element for link previews */
let previewTooltip = null;

/**
 * Initialize link hover preview listeners on a container.
 * Shows a small tooltip with the URL on hover.
 *
 * @param {HTMLElement} container - Container to attach listeners to
 */
export function initLinkPreviews(container) {
  if (!container) return;

  container.addEventListener("mouseover", handleLinkMouseOver);
  container.addEventListener("mouseout", handleLinkMouseOut);
  container.addEventListener("focusin", handleLinkMouseOver);
  container.addEventListener("focusout", handleLinkMouseOut);
}

/**
 * Initialize code block copy button listeners on a container.
 * Uses event delegation so dynamically rendered code blocks work.
 *
 * @param {HTMLElement} container - Container to attach listeners to
 */
export function initCodeBlockCopy(container) {
  if (!container) return;

  container.addEventListener("click", handleCodeCopyClick);
}

/**
 * Handle mouseover on rendered links to show preview tooltip.
 * @param {Event} e - Mouse event
 */
function handleLinkMouseOver(e) {
  const link = e.target.closest("a.rendered-link[data-url]");
  if (!link) return;

  const url = link.getAttribute("data-url");
  if (!url) return;

  if (!previewTooltip) {
    previewTooltip = document.createElement("div");
    previewTooltip.className = "link-preview-tooltip";
    previewTooltip.setAttribute("role", "tooltip");
    document.body.appendChild(previewTooltip);
  }

  // Parse URL for display
  let displayUrl;
  try {
    const parsed = new URL(url);
    displayUrl = `${parsed.hostname}${parsed.pathname === "/" ? "" : parsed.pathname}`;
  } catch {
    displayUrl = url;
  }

  previewTooltip.textContent = displayUrl;
  previewTooltip.classList.add("visible");

  // Position near the link
  const rect = link.getBoundingClientRect();
  previewTooltip.style.top = `${rect.bottom + window.scrollY + 4}px`;
  previewTooltip.style.left = `${rect.left + window.scrollX}px`;
}

/**
 * Handle mouseout to hide preview tooltip.
 * @param {Event} e - Mouse event
 */
function handleLinkMouseOut(e) {
  const link = e.target.closest("a.rendered-link[data-url]");
  if (!link) return;

  if (previewTooltip) {
    previewTooltip.classList.remove("visible");
  }
}

// ---------------------------------------------------------------------------
// Code Block Copy Handler
// ---------------------------------------------------------------------------

/**
 * Handle click on code block copy buttons.
 * Copies the code content to clipboard and shows feedback.
 *
 * @param {Event} e - Click event
 */
function handleCodeCopyClick(e) {
  const btn = e.target.closest(".code-copy-btn");
  if (!btn) return;

  const blockId = btn.getAttribute("data-code-block-id");
  if (!blockId) return;

  const wrapper = btn.closest(".code-block-wrapper");
  if (!wrapper) return;

  const codeEl = wrapper.querySelector("pre code");
  if (!codeEl) return;

  const text = codeEl.textContent || "";

  navigator.clipboard.writeText(text).then(
    () => {
      // Show success feedback
      const label = btn.querySelector(".code-copy-label");
      const icon = btn.querySelector(".code-copy-icon");
      if (label) label.textContent = "Copied!";
      if (icon) icon.textContent = "✅";
      btn.classList.add("copied");

      setTimeout(() => {
        if (label) label.textContent = "Copy";
        if (icon) icon.textContent = "📋";
        btn.classList.remove("copied");
      }, 2000);
    },
    (err) => {
      console.warn("Failed to copy code to clipboard:", err);
      // Fallback: select text
      const range = document.createRange();
      range.selectNodeContents(codeEl);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    },
  );
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

/**
 * Escape HTML entities in text content.
 * @param {string} text - Raw text
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Escape a string for safe use inside an HTML attribute.
 * @param {string} value - Raw attribute value
 * @returns {string} Escaped value
 */
function escapeAttr(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ---------------------------------------------------------------------------
// Math Expression Processing (Requirement 16.5)
// ---------------------------------------------------------------------------

/**
 * Pre-process math expressions in Markdown text before Marked parsing.
 * Replaces $$ ... $$ (display) and $ ... $ (inline) with placeholder tokens
 * so Marked doesn't mangle the LaTeX syntax.
 *
 * @param {string} text - Raw Markdown text
 * @returns {{ text: string, mathBlocks: Array<{ id: string, tex: string, display: boolean }> }}
 */
function extractMathExpressions(text) {
  const mathBlocks = [];
  let counter = 0;

  // Replace display math ($$...$$) first — greedy across newlines
  let processed = text.replace(/\$\$([\s\S]+?)\$\$/g, (_match, tex) => {
    const id = `__MATH_BLOCK_${counter++}__`;
    mathBlocks.push({ id, tex: tex.trim(), display: true });
    return id;
  });

  // Replace inline math ($...$) — single line only, not preceded/followed by $
  processed = processed.replace(
    /(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)/g,
    (_match, tex) => {
      const id = `__MATH_BLOCK_${counter++}__`;
      mathBlocks.push({ id, tex: tex.trim(), display: false });
      return id;
    },
  );

  return { text: processed, mathBlocks };
}

/**
 * Replace math placeholder tokens in rendered HTML with KaTeX output.
 * Falls back to displaying raw LaTeX in a <code> tag if KaTeX is unavailable.
 *
 * @param {string} html - Rendered HTML containing math placeholders
 * @param {Array<{ id: string, tex: string, display: boolean }>} mathBlocks - Extracted math blocks
 * @returns {string} HTML with rendered math expressions
 */
function restoreMathExpressions(html, mathBlocks) {
  let result = html;

  for (const block of mathBlocks) {
    let rendered;

    if (katex) {
      try {
        rendered = katex.renderToString(block.tex, {
          displayMode: block.display,
          throwOnError: false,
          output: "htmlAndMathml",
          trust: false,
        });
      } catch {
        // KaTeX render failed — show raw LaTeX
        rendered = block.display
          ? `<div class="math-display math-error"><code>${escapeHtml(block.tex)}</code></div>`
          : `<code class="math-inline math-error">${escapeHtml(block.tex)}</code>`;
      }
    } else {
      // KaTeX not loaded — show raw LaTeX in styled code
      rendered = block.display
        ? `<div class="math-display math-fallback"><code>${escapeHtml(block.tex)}</code></div>`
        : `<code class="math-inline math-fallback">${escapeHtml(block.tex)}</code>`;
    }

    // Wrap in appropriate container
    if (katex && rendered) {
      rendered = block.display
        ? `<div class="math-display">${rendered}</div>`
        : `<span class="math-inline">${rendered}</span>`;
    }

    result = result.replace(block.id, rendered);
  }

  return result;
}

// ---------------------------------------------------------------------------
// Mermaid Diagram Post-Processing (Requirement 16.6)
// ---------------------------------------------------------------------------

/**
 * Process all Mermaid diagram placeholders in a container element.
 * Renders each mermaid code block into an SVG diagram.
 *
 * @param {HTMLElement} container - Container with mermaid-wrapper elements
 * @returns {Promise<void>}
 */
export async function renderMermaidDiagrams(container) {
  if (!container) return;

  const wrappers = container.querySelectorAll(".mermaid-wrapper");
  if (wrappers.length === 0) return;

  const mermaidInstance = await getMermaid();
  if (!mermaidInstance) {
    // Mark diagrams as fallback (show raw code)
    wrappers.forEach((wrapper) => {
      wrapper.classList.add("mermaid-fallback");
    });
    return;
  }

  for (const wrapper of wrappers) {
    const diagramEl = wrapper.querySelector(".mermaid-diagram");
    if (!diagramEl) continue;

    const diagramId = wrapper.getAttribute("data-mermaid-id");
    const code = diagramEl.textContent || "";

    try {
      const { svg } = await mermaidInstance.render(
        diagramId || `mermaid-${Date.now()}`,
        code,
      );
      diagramEl.innerHTML = svg;
      wrapper.classList.add("mermaid-rendered");
    } catch (err) {
      console.warn("Mermaid diagram render failed:", err);
      wrapper.classList.add("mermaid-error");
      diagramEl.innerHTML =
        `<div class="mermaid-error-msg">` +
        `<span class="mermaid-error-icon" aria-hidden="true">⚠️</span>` +
        `<span>Diagram rendering failed</span>` +
        `</div>` +
        `<pre class="mermaid-source"><code>${escapeHtml(code)}</code></pre>`;
    }
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Render a Markdown string to sanitized HTML.
 *
 * Falls back to basic HTML-escaped text if Marked.js is unavailable.
 * Processes LaTeX math expressions via KaTeX (Requirement 16.5).
 * Mermaid diagrams are rendered as placeholders — call renderMermaidDiagrams()
 * on the container after inserting the HTML into the DOM.
 *
 * @param {string} markdown - Raw Markdown text
 * @returns {Promise<string>} Sanitized HTML string
 */
export async function renderMarkdown(markdown) {
  if (!markdown) return "";

  const mod = await getMarked();

  if (!mod) {
    // Fallback: escape HTML and convert newlines
    return escapeHtml(markdown).replace(/\n/g, "<br>");
  }

  // Extract math expressions before Marked parsing (Requirement 16.5)
  const { text: preprocessed, mathBlocks } = extractMathExpressions(markdown);

  const rawHtml = mod.marked.parse(preprocessed);
  let html = sanitizeHtml(rawHtml);

  // Restore math expressions with KaTeX rendering
  if (mathBlocks.length > 0) {
    html = restoreMathExpressions(html, mathBlocks);
  }

  return html;
}

/**
 * Render Markdown synchronously (requires Marked.js to be pre-loaded).
 * Returns escaped text if Marked is not yet loaded.
 * Processes LaTeX math expressions via KaTeX (Requirement 16.5).
 *
 * @param {string} markdown - Raw Markdown text
 * @returns {string} Sanitized HTML string
 */
export function renderMarkdownSync(markdown) {
  if (!markdown) return "";

  if (!markedInitialized || !marked) {
    return escapeHtml(markdown).replace(/\n/g, "<br>");
  }

  // Extract math expressions before Marked parsing
  const { text: preprocessed, mathBlocks } = extractMathExpressions(markdown);

  const rawHtml = marked.marked.parse(preprocessed);
  let html = sanitizeHtml(rawHtml);

  // Restore math expressions with KaTeX rendering
  if (mathBlocks.length > 0) {
    html = restoreMathExpressions(html, mathBlocks);
  }

  return html;
}

/**
 * Pre-load Marked.js, Highlight.js, KaTeX, and Mermaid.js so that
 * synchronous rendering is available.
 * Call this during application initialization.
 *
 * @returns {Promise<boolean>} Whether core loading (Marked.js) succeeded
 */
export async function initRenderer() {
  // Load Highlight.js first so the custom code renderer can use it
  const hljsInstance = await getHljs();
  if (hljsInstance) {
    console.log("Highlight.js loaded for syntax highlighting");
  } else {
    console.warn(
      "Highlight.js unavailable – code blocks will not be highlighted",
    );
  }

  // Load KaTeX for math rendering (Requirement 16.5)
  const katexInstance = await getKatex();
  if (katexInstance) {
    console.log("KaTeX loaded for math expression rendering");
  } else {
    console.warn("KaTeX unavailable – math expressions will show raw LaTeX");
  }

  // Load Mermaid.js for diagram rendering (Requirement 16.6)
  const mermaidInstance = await getMermaid();
  if (mermaidInstance) {
    console.log("Mermaid.js loaded for diagram rendering");
  } else {
    console.warn("Mermaid.js unavailable – diagrams will show raw code");
  }

  const mod = await getMarked();
  if (mod) {
    console.log("Renderer module initialized with Marked.js (GFM enabled)");
    return true;
  }
  console.warn("Renderer module initialized in fallback mode (no Marked.js)");
  return false;
}

// Default export for convenience
export default {
  renderMarkdown,
  renderMarkdownSync,
  sanitizeHtml,
  initRenderer,
  initLinkPreviews,
  initCodeBlockCopy,
  renderMermaidDiagrams,
};
