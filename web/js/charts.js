// Inline-SVG charts, no library.
//
// Every chart here plots one series, so colour carries no identity: a single
// navy fill (#1e3a8a, >= 3:1 on white) with direct value labels and recessive
// axes. The same choice the Streamlit app makes with Plotly, and it keeps the
// charts readable for colour-blind viewers and in print. Each chart ships a
// hover tooltip and a "Show data" table, so no value is reachable only by eye.

const NAVY = "#1e3a8a";
const PAD = { top: 22, right: 18, bottom: 46, left: 52 };

function el(tag, attrs = {}, children = []) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value !== null && value !== undefined) node.setAttribute(key, String(value));
  }
  for (const child of [].concat(children)) {
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

function niceCeiling(value) {
  if (value <= 5) return Math.max(1, Math.ceil(value));
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / (magnitude / 2)) * (magnitude / 2);
}

function ticks(max, count = 4) {
  // Counts are whole numbers, so "2.3 queries" on an axis is noise. Use one
  // tick per unit while the range is small enough for that to stay readable.
  if (Number.isInteger(max) && max <= 6) {
    return Array.from({ length: max + 1 }, (_, index) => index);
  }
  if (Number.isInteger(max)) {
    const step = Math.max(1, Math.ceil(max / count));
    const result = [];
    for (let value = 0; value <= max; value += step) result.push(value);
    return result;
  }
  const step = max / count;
  return Array.from({ length: count + 1 }, (_, index) => Math.round(index * step * 100) / 100);
}

/** A rounded-top bar: flat where it meets the baseline, 4px radius on top. */
function barPath(x, y, width, height, radius = 4) {
  const r = Math.min(radius, width / 2, Math.max(0, height));
  if (height <= 0.5) return `M${x} ${y}h${width}`;
  return `M${x} ${y + height}V${y + r}a${r} ${r} 0 0 1 ${r} ${-r}h${width - 2 * r}` +
    `a${r} ${r} 0 0 1 ${r} ${r}V${y + height}Z`;
}

function tooltip() {
  let node = document.querySelector(".chart-tip");
  if (!node) {
    node = document.createElement("div");
    node.className = "chart-tip";
    node.setAttribute("role", "status");
    document.body.appendChild(node);
  }
  return node;
}

function attachTip(target, label) {
  const show = (event) => {
    const tip = tooltip();
    tip.textContent = label;
    tip.style.opacity = "1";
    const bounds = target.getBoundingClientRect();
    tip.style.left = `${bounds.left + bounds.width / 2 + window.scrollX}px`;
    tip.style.top = `${bounds.top + window.scrollY - 10}px`;
    if (event && event.type === "focus") target.setAttribute("data-focused", "true");
  };
  const hide = () => { tooltip().style.opacity = "0"; target.removeAttribute("data-focused"); };
  target.addEventListener("mouseenter", show);
  target.addEventListener("mousemove", show);
  target.addEventListener("mouseleave", hide);
  target.addEventListener("focus", show);
  target.addEventListener("blur", hide);
  target.setAttribute("tabindex", "0");
  target.setAttribute("role", "img");
  target.setAttribute("aria-label", label);
}

function dataTable(rows, labelHeading, valueHeading) {
  const details = document.createElement("details");
  details.className = "acc chart-data";
  const summary = document.createElement("summary");
  summary.textContent = "Show data";
  details.appendChild(summary);

  const wrap = document.createElement("div");
  wrap.className = "acc-body";
  const table = document.createElement("table");
  table.innerHTML =
    `<thead><tr><th>${labelHeading}</th><th class="num">${valueHeading}</th></tr></thead><tbody>` +
    rows.map((row) => `<tr><td>${escapeHtml(row.label)}</td><td class="num">${row.display ?? row.value}</td></tr>`).join("") +
    "</tbody>";
  wrap.appendChild(table);
  details.appendChild(wrap);
  return details;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]
  ));
}

function frame(title) {
  const figure = document.createElement("figure");
  figure.className = "chart";
  figure.style.margin = "0 0 1.4rem";
  if (title) {
    const caption = document.createElement("figcaption");
    caption.className = "chart-title";
    caption.textContent = title;
    figure.appendChild(caption);
  }
  return figure;
}

/**
 * Vertical bars for counts over a category axis (days, bands, activities).
 * rows: [{ label, value, display? }]
 */
export function barChart(rows, { title, xTitle, yTitle, color = NAVY, height = 260,
  valueSuffix = "", labelHeading = "Category", valueHeading = "Count" } = {}) {
  const figure = frame(title);
  if (!rows.length) {
    figure.appendChild(Object.assign(document.createElement("p"),
      { className: "caption", textContent: "No data for this period." }));
    return figure;
  }

  const width = 760;
  const plotWidth = width - PAD.left - PAD.right;
  const plotHeight = height - PAD.top - PAD.bottom;
  const max = niceCeiling(Math.max(...rows.map((row) => row.value), 1));
  const slot = plotWidth / rows.length;
  // Narrow bars when there are few of them, so one day of data is not a slab.
  const barWidth = Math.max(6, Math.min(slot - 10, rows.length <= 3 ? 84 : slot * 0.68));

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "xMidYMid meet",
    role: "img", "aria-label": title || "Bar chart",
  });

  for (const tick of ticks(max)) {
    const y = PAD.top + plotHeight - (tick / max) * plotHeight;
    svg.appendChild(el("line", { class: "grid-line", x1: PAD.left, x2: width - PAD.right, y1: y, y2: y }));
    svg.appendChild(el("text", { class: "tick", x: PAD.left - 9, y: y + 4, "text-anchor": "end" },
      String(Math.round(tick * 10) / 10)));
  }
  svg.appendChild(el("line", {
    class: "axis-line", x1: PAD.left, x2: width - PAD.right,
    y1: PAD.top + plotHeight, y2: PAD.top + plotHeight,
  }));

  rows.forEach((row, index) => {
    const barHeight = (row.value / max) * plotHeight;
    const x = PAD.left + index * slot + (slot - barWidth) / 2;
    const y = PAD.top + plotHeight - barHeight;
    const bar = el("path", { d: barPath(x, y, barWidth, barHeight), fill: color });
    attachTip(bar, `${row.label}: ${row.display ?? row.value}${valueSuffix}`);
    svg.appendChild(bar);

    if (row.value > 0) {
      svg.appendChild(el("text", {
        class: "bar-label", x: x + barWidth / 2, y: y - 6, "text-anchor": "middle",
      }, String(row.display ?? row.value)));
    }
    svg.appendChild(el("text", {
      class: "tick", x: x + barWidth / 2, y: PAD.top + plotHeight + 18, "text-anchor": "middle",
    }, row.label));
  });

  if (yTitle) {
    svg.appendChild(el("text", {
      class: "axis-title", x: 12, y: PAD.top + plotHeight / 2,
      "text-anchor": "middle", transform: `rotate(-90 12 ${PAD.top + plotHeight / 2})`,
    }, yTitle));
  }
  if (xTitle) {
    svg.appendChild(el("text", {
      class: "axis-title", x: PAD.left + plotWidth / 2, y: height - 8, "text-anchor": "middle",
    }, xTitle));
  }

  figure.appendChild(svg);
  figure.appendChild(dataTable(rows, labelHeading, valueHeading));
  return figure;
}

/**
 * Horizontal bars, for long labels and ranked lists (document pairs, query
 * types). rows: [{ label, value, display? }]
 */
export function horizontalBarChart(rows, { title, xTitle, color = NAVY, max: fixedMax,
  labelWidth = 260, labelHeading = "Item", valueHeading = "Value" } = {}) {
  const figure = frame(title);
  if (!rows.length) {
    figure.appendChild(Object.assign(document.createElement("p"),
      { className: "caption", textContent: "Not enough data yet." }));
    return figure;
  }

  const width = 760;
  const rowHeight = 30;
  const height = rows.length * rowHeight + 46;
  const plotWidth = width - labelWidth - 56;
  const max = fixedMax || niceCeiling(Math.max(...rows.map((row) => row.value), 1));

  const svg = el("svg", {
    viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: "xMidYMid meet",
    role: "img", "aria-label": title || "Bar chart",
  });

  // A label longer than its gutter would run off the left of the figure, so
  // shorten it here; the tooltip and the data table still carry it in full.
  const maxLabelChars = Math.floor(labelWidth / 6.2);
  const shorten = (label) => (label.length <= maxLabelChars
    ? label
    : `${label.slice(0, maxLabelChars - 1).trimEnd()}…`);

  rows.forEach((row, index) => {
    const y = index * rowHeight + 8;
    const barWidth = Math.max(1, (row.value / max) * plotWidth);
    svg.appendChild(el("text", {
      class: "tick", x: labelWidth - 10, y: y + 15, "text-anchor": "end",
    }, shorten(row.label)));
    // Rounded on the free end only, flat against the axis it grows from.
    const bar = el("path", {
      d: `M${labelWidth} ${y + 3}h${Math.max(0, barWidth - 4)}a4 4 0 0 1 4 4v8a4 4 0 0 1 -4 4` +
        `H${labelWidth}Z`,
      fill: color,
    });
    attachTip(bar, `${row.label}: ${row.display ?? row.value}`);
    svg.appendChild(bar);
    svg.appendChild(el("text", {
      class: "bar-label", x: labelWidth + barWidth + 8, y: y + 15,
    }, String(row.display ?? row.value)));
  });

  svg.appendChild(el("line", {
    class: "axis-line", x1: labelWidth, x2: labelWidth, y1: 4, y2: rows.length * rowHeight + 4,
  }));
  if (xTitle) {
    svg.appendChild(el("text", {
      class: "axis-title", x: labelWidth + plotWidth / 2, y: height - 8, "text-anchor": "middle",
    }, xTitle));
  }

  figure.appendChild(svg);
  figure.appendChild(dataTable(rows, labelHeading, valueHeading));
  return figure;
}
