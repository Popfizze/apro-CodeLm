import { addDays, daysBetween, formatDay, formatMoney, html, isoDay, raw, truncate } from "./ui.js";

const BAR_MAX = 24;
const GAP = 2;

export const TONE_GLYPHS = { critical: "✕", warning: "!", info: "i", positive: "✓", neutral: "–" };

function scale(domainStart, domainEnd, rangeStart, rangeEnd) {
  const span = domainEnd - domainStart || 1;
  return (value) => rangeStart + ((value - domainStart) / span) * (rangeEnd - rangeStart);
}

function niceMax(value, step) {
  return Math.max(step, Math.ceil(value / step) * step);
}

function frame(width, height, label, content) {
  return html`<svg
    class="chart-svg"
    width="${width}"
    height="${height}"
    viewBox="0 0 ${width} ${height}"
    role="img"
    aria-label="${label}"
  >
    ${content}
  </svg>`;
}

function tipAttrs(lines) {
  return raw(
    `data-tip="${lines.filter(Boolean).join("\n").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;")}"`,
  );
}

function linked(target, content, lines) {
  if (!target) return html`<g class="mark" tabindex="0" ${tipAttrs(lines)}>${content}</g>`;
  return html`<a class="mark" href="${target}" ${tipAttrs(lines)}>${content}</a>`;
}

export function hbarPath({ x, y, width, height, roundEnd }) {
  const w = Math.max(0, width);
  const r = roundEnd ? Math.min(4, w, height / 2) : 0;
  return `M${x},${y}h${w - r}q${r},0 ${r},${r}v${height - 2 * r}q0,${r} ${-r},${r}h${-(w - r)}z`;
}

export function vbarPath({ x, bottom, width, height, roundEnd }) {
  const h = Math.max(0, height);
  const r = roundEnd ? Math.min(4, h, width / 2) : 0;
  return `M${x},${bottom}v${-(h - r)}q0,${-r} ${r},${-r}h${width - 2 * r}q${r},0 ${r},${r}v${h - r}z`;
}

function axisText(x, y, value, anchor = "middle") {
  return html`<text class="axis-text" x="${x}" y="${y}" text-anchor="${anchor}">${value}</text>`;
}

function gridLine(x1, y1, x2, y2) {
  return html`<line class="grid-line" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" />`;
}

export function legend(items) {
  return html`<ul class="legend">
    ${items.map(
      (item) =>
        html`<li>
          <span class="swatch ${item.className}"></span>${item.label}${
            item.total != null ? html` <b>${item.total}</b>` : ""
          }
        </li>`,
    )}
  </ul>`;
}

export function windowChart({ width, today, golive, contractEnd, refs }) {
  const height = 56;
  const start = isoDay(today);
  const end = isoDay(contractEnd) || addDays(start, 30);
  const x = scale(0, Math.max(1, daysBetween(start, end)), 12, width - 12);
  const at = (day) => x(daysBetween(start, day));
  const margin = golive ? daysBetween(golive, end) : null;
  const marks = [
    {
      day: start,
      kind: "today",
      label: `Aujourd'hui · ${formatDay(start, { year: false })}`,
      x: at(start),
      y: 53,
      anchor: "start",
    },
    {
      day: golive,
      kind: "golive",
      label: `Mise en production · ${formatDay(golive, { year: false })}`,
      x: at(golive) - 10,
      y: 16,
      anchor: "end",
    },
    {
      day: end,
      kind: "end",
      label: `Fin du contrat · ${formatDay(end, { year: false })}`,
      x: at(end),
      y: 16,
      anchor: "end",
    },
  ].filter((mark) => mark.day);
  return frame(
    width,
    height,
    "Fenêtre de mise en production",
    html`<rect class="fill-track" x="12" y="26" width="${width - 24}" height="8" rx="4" /> ${
        golive && margin > 0
          ? html`<path class="brace" d="M${at(golive)},40 v4 H${at(end)} v-4" />
              <text class="axis-text is-ink" x="${(at(golive) + at(end)) / 2}" y="53" text-anchor="middle"
                >${margin} jours</text
              >`
          : ""
      }
      ${marks.map((mark) => windowMark(mark, at(mark.day), refs))}
      ${marks.map((mark) => axisText(mark.x, mark.y, mark.label, mark.anchor))}`,
  );
}

function windowMark(mark, cx, refs) {
  const tip = [formatDay(mark.day), mark.label.split(" · ")[0], refs?.[mark.kind] || ""];
  if (mark.kind === "today") {
    return linked("", html`<line class="today-line" x1="${cx}" y1="18" x2="${cx}" y2="40" />`, tip);
  }
  if (mark.kind === "golive") {
    return linked(
      "",
      html`<rect
        class="fill-indigo"
        x="${cx - 6}"
        y="24"
        width="12"
        height="12"
        transform="rotate(45 ${cx} 30)"
      />`,
      tip,
    );
  }
  return linked("", html`<rect class="fill-navy" x="${cx - 2}" y="22" width="4" height="16" rx="1" />`, tip);
}

function nodeGlyph(cx, cy, tone) {
  return html`<text class="node-glyph is-${tone}" x="${cx}" y="${cy + 3.5}" text-anchor="middle"
    >${TONE_GLYPHS[tone]}</text
  >`;
}

function chainRow(row, index, layout) {
  const cy = index * layout.rowHeight + Math.max(20, layout.rowHeight / 2 - (layout.detail ? 8 : 4));
  const nodes = [...row.nodes, { id: "validation", label: row.validator, final: true }];
  const step = Math.min(120, (layout.width - layout.labelWidth - 40) / Math.max(1, nodes.length - 1 || 1));
  const xOf = (position) => layout.labelWidth + 16 + position * step;
  return html`<g class="chain-row">
    ${linked(
      row.href,
      html`<text class="chain-label" x="0" y="${cy + 4}">${row.id}</text>
        <text class="axis-text" x="28" y="${cy + 4}">${truncate(row.label, layout.labelChars)}</text>
        ${layout.detail ? html`<text class="axis-text is-critical" x="28" y="${cy + 20}">${truncate(row.state, layout.labelChars)}</text>` : ""}`,
      [row.id, row.label, row.state],
    )}
    <line class="edge" x1="${xOf(0)}" y1="${cy}" x2="${xOf(nodes.length - 1)}" y2="${cy}" />
    ${nodes.map((node, position) => chainNode(node, xOf(position), cy))}
  </g>`;
}

function chainNode(node, cx, cy) {
  if (node.final) {
    return linked(
      node.href,
      html`<rect class="node-final" x="${cx - 8}" y="${cy - 8}" width="16" height="16" rx="4" />
        <text class="axis-text" x="${cx}" y="${cy + 19}" text-anchor="middle">Validation</text>`,
      ["Validation", node.label],
    );
  }
  return linked(
    node.href,
    html`<circle class="node is-${node.tone}" cx="${cx}" cy="${cy}" r="8" />${nodeGlyph(cx, cy, node.tone)}
      <text class="axis-text is-ink" x="${cx}" y="${cy + 19}" text-anchor="middle">${node.id}</text>`,
    [node.id, node.label, node.owner, node.due, node.status],
  );
}

export function chainChart({ width, rows, detail = false, available = 0 }) {
  const maxNodes = Math.max(1, ...rows.map((row) => row.nodes.length + 1));
  const labelWidth = Math.max(160, Math.min(width * 0.6, width - (maxNodes - 1) * 120 - 56));
  const layout = {
    width,
    detail,
    rowHeight: Math.max(detail ? 64 : 34, (available - 8) / Math.max(1, rows.length)),
    labelWidth,
    labelChars: Math.floor((labelWidth - 36) / 6.4),
  };
  const height = rows.length * layout.rowHeight + 8;
  return frame(
    width,
    height,
    "Chaîne des conditions de mise en production",
    rows.map((row, index) => chainRow(row, index, layout)),
  );
}

export function budgetMeter(segments, total) {
  return html`<div class="meter" role="img" aria-label="Autorisé, facturé et payé">
    ${segments
      .filter((segment) => segment.amount > 0)
      .map(
        (segment) =>
          html`<span
            class="meter-seg ${segment.className}"
            style="flex-grow:${segment.amount / total}"
            ${tipAttrs([formatMoney(segment.amount), segment.label])}
          ></span>`,
      )}
  </div>`;
}

export function riskMatrix({ width, probabilities, impacts, risks, available = 0 }) {
  const labelWidth = 70;
  const headHeight = 18;
  const cellWidth = (width - labelWidth) / Math.max(1, impacts.length);
  const cellHeight = Math.max(30, (available - headHeight - 2) / Math.max(1, probabilities.length));
  const height = headHeight + cellHeight * probabilities.length;
  const cells = probabilities.flatMap((probability, row) =>
    impacts.map((impact, column) =>
      riskCell({ probability, impact, row, column, risks, cellWidth, cellHeight, labelWidth, headHeight }),
    ),
  );
  return frame(
    width,
    height,
    "Matrice des risques",
    html`${impacts.map((impact, column) => axisText(labelWidth + column * cellWidth + cellWidth / 2, 12, `Impact ${impact}`))}
    ${probabilities.map((probability, row) => axisText(labelWidth - 8, headHeight + row * cellHeight + cellHeight / 2 + 4, probability, "end"))}
    ${cells}`,
  );
}

function riskCell({
  probability,
  impact,
  row,
  column,
  risks,
  cellWidth,
  cellHeight,
  labelWidth,
  headHeight,
}) {
  const x = labelWidth + column * cellWidth;
  const y = headHeight + row * cellHeight;
  const inside = risks.filter((risk) => risk.probability === probability && risk.impact === impact);
  const perRow = Math.max(1, Math.floor((cellWidth - 12) / 64));
  const rows = Math.ceil(inside.length / perRow);
  const top = y + cellHeight / 2 - ((rows - 1) * 18) / 2;
  return html`<rect class="matrix-cell" x="${x}" y="${y}" width="${cellWidth}" height="${cellHeight}" />
    ${inside.map((risk, index) =>
      riskPoint(risk, x + 14 + (index % perRow) * 64, top + Math.floor(index / perRow) * 18),
    )}`;
}

function riskPoint(risk, cx, cy) {
  return linked(
    risk.href,
    html`<circle class="${risk.closed ? "point-closed" : "point-open"}" cx="${cx}" cy="${cy}" r="6" />
      <text class="axis-text is-ink" x="${cx + 10}" y="${cy + 4}">${risk.id} ${risk.trendGlyph}</text>`,
    [
      risk.id,
      risk.statement,
      `Propriétaire : ${risk.owner}`,
      `Registre : ${risk.registerStatus}`,
      risk.actualState,
    ],
  );
}

function stackedHBar({ y, segments, x0, xOf, height, href, totalLabel }) {
  let cursor = x0;
  const parts = segments.map((segment, index) => {
    const width = Math.max(0, xOf(segment.amount) - x0 - (index < segments.length - 1 ? GAP : 0));
    const path = hbarPath({ x: cursor, y, width, height, roundEnd: index === segments.length - 1 });
    const label =
      width >= 48 && segment.showLabel !== false
        ? segmentLabel(cursor + width / 2, y + height / 2 + 4, segment)
        : "";
    const part = linked(href, html`<path class="${segment.className}" d="${path}" />${label}`, segment.tip);
    cursor += width + GAP;
    return part;
  });
  return html`${parts}${totalLabel ? axisText(cursor + 4, y + height / 2 + 4, totalLabel, "start") : ""}`;
}

function segmentLabel(x, y, segment) {
  return html`<text class="segment-label ${segment.labelClass || ""}" x="${x}" y="${y}" text-anchor="middle"
    >${segment.label}</text
  >`;
}

export function invoiceChart({ width, invoices, maxAmount, step, available = 0 }) {
  const labelWidth = 64;
  const right = 72;
  const rowHeight = Math.max(34, (available - 24) / Math.max(1, invoices.length));
  const top = 6;
  const max = niceMax(maxAmount, step);
  const xOf = scale(0, max, 0, width - labelWidth - right);
  const height = top + invoices.length * rowHeight + 18;
  const ticks = [];
  for (let value = 0; value <= max; value += step) ticks.push(value);
  return frame(
    width,
    height,
    "Factures par ligne",
    html`${ticks.map((value) => gridLine(labelWidth + xOf(value), top, labelWidth + xOf(value), height - 18))}
    ${ticks.map((value) => axisText(labelWidth + xOf(value), height - 4, value ? `${value / 1000} k$` : "0"))}
    ${invoices.map((invoice, index) => {
      const y = top + index * rowHeight + (rowHeight - BAR_MAX) / 2;
      return html`${axisText(labelWidth - 8, y + BAR_MAX / 2 + 4, invoice.id, "end")}
      ${stackedHBar({
        y,
        segments: invoice.segments,
        x0: labelWidth,
        xOf: (amount) => labelWidth + xOf(amount),
        height: BAR_MAX,
        href: invoice.href,
        totalLabel: formatMoney(invoice.amount),
      })}`;
    })}`,
  );
}

export function dotStrip({ width, days, today, available = 0 }) {
  const dot = 8;
  const top = 6;
  const maxCount = Math.max(1, ...days.map((day) => day.items.length));
  const pitch = Math.max(10, Math.min(16, (available - top - 24) / maxCount));
  const height = top + maxCount * pitch + 22;
  const column = width / days.length;
  return frame(
    width,
    height,
    "Faits des derniers jours",
    html`${days.map((day, index) => {
      const cx = column * index + column / 2;
      const bottom = height - 22;
      return html`<g>
        ${day.items.map((item, position) =>
          linked(
            day.href,
            html`<circle
              class="dot ${item.className}"
              cx="${cx}"
              cy="${bottom - position * pitch - dot / 2}"
              r="${dot / 2 + 0.5}"
            />`,
            [item.time || formatDay(day.day), item.label, item.summary, item.ref],
          ),
        )}
        ${axisText(cx, height - 6, formatDay(day.day, { year: false }).replace(" sept.", "").replace(" ", " "))}
        ${day.day === today ? html`<line class="today-line" x1="${cx}" y1="${top}" x2="${cx}" y2="${bottom}" />` : ""}
      </g>`;
    })}`,
  );
}

function monthTicks(startDay, count) {
  const ticks = [];
  for (let offset = 0; offset < count; offset += 1) {
    const day = addDays(startDay, offset);
    if (day.endsWith("-01") || day.endsWith("-15")) ticks.push({ offset, day });
  }
  return ticks;
}

function columnStack({ column, cx, barWidth, bottom, yOf, active }) {
  let base = bottom;
  const visible = column.stack.filter((part) => part.count > 0);
  const marks = visible.map((part, index) => {
    const height = yOf(0) - yOf(part.count) - (index < visible.length - 1 ? GAP : 0);
    const path = vbarPath({
      x: cx - barWidth / 2,
      bottom: base,
      width: barWidth,
      height,
      roundEnd: index === visible.length - 1,
    });
    base -= height + GAP;
    return html`<path class="${part.className}" d="${path}" />`;
  });
  const total = column.stack.reduce((sum, part) => sum + part.count, 0);
  const outline =
    active && total
      ? html`<rect
          class="active-outline"
          x="${cx - barWidth / 2 - 3}"
          y="${yOf(total) - 3}"
          width="${barWidth + 6}"
          height="${bottom - yOf(total) + 3}"
          rx="4"
        />`
      : "";
  return { marks, outline, total };
}

export function dayHistogram({ width, columns, undated, today, activeDay, legendTotals: _legendTotals }) {
  const height = 220;
  const left = 32;
  const undatedWidth = undated ? 56 : 0;
  const plotLeft = left + undatedWidth;
  const bottom = height - 26;
  const top = 18;
  const max = Math.max(1, ...columns.map((column) => column.total), undated?.total || 0);
  const yOf = scale(0, max, bottom, top);
  const pitch = (width - plotLeft - 8) / Math.max(1, columns.length);
  const barWidth = Math.max(3, Math.min(BAR_MAX, pitch - GAP));
  const ticks = [];
  for (let value = 0; value <= max; value += Math.max(1, Math.ceil(max / 4))) ticks.push(value);
  const todayIndex = columns.findIndex((column) => column.day === today);
  const todayX = todayIndex >= 0 ? plotLeft + pitch * todayIndex + pitch / 2 : null;
  return frame(
    width,
    height,
    "Événements par jour",
    html`${ticks.map((value) => html`${gridLine(left, yOf(value), width - 8, yOf(value))}${axisText(left - 8, yOf(value) + 4, value, "end")}`)}
    ${undated ? undatedColumn({ undated, left, undatedWidth, bottom, yOf, barWidth: Math.min(BAR_MAX, 20), active: activeDay === "non-date" }) : ""}
    ${columns.map((column, index) => histogramColumn({ column, cx: plotLeft + pitch * index + pitch / 2, barWidth, bottom, yOf, active: column.day === activeDay }))}
    ${monthTicks(columns[0]?.day, columns.length).map((tick) => axisText(plotLeft + pitch * tick.offset + pitch / 2, height - 8, formatDay(tick.day, { year: false })))}
    ${
      todayX != null
        ? html`<line
              class="today-line is-dashed"
              x1="${todayX}"
              y1="${top - 8}"
              x2="${todayX}"
              y2="${bottom}"
            />
            <text class="axis-text is-ink" x="${todayX - 6}" y="${top - 6}" text-anchor="end"
              >Aujourd'hui · ${formatDay(today, { year: false })}</text
            >`
        : ""
    }`,
  );
}

function histogramColumn({ column, cx, barWidth, bottom, yOf, active }) {
  const stack = columnStack({ column, cx, barWidth, bottom, yOf, active });
  const hitTop = Math.min(yOf(stack.total), bottom - 24);
  const tip = [
    `${stack.total} élément${stack.total > 1 ? "s" : ""}`,
    formatDay(column.day),
    ...column.stack.filter((part) => part.count).map((part) => `${part.label} : ${part.count}`),
  ];
  if (!stack.total) return "";
  return linked(
    column.href,
    html`<rect
        class="hit"
        x="${cx - Math.max(barWidth, 12) / 2}"
        y="${hitTop}"
        width="${Math.max(barWidth, 12)}"
        height="${bottom - hitTop}"
      />${stack.outline}${stack.marks}`,
    tip,
  );
}

function undatedColumn({ undated, left, undatedWidth, bottom, yOf, barWidth, active }) {
  const cx = left + undatedWidth / 2 - 6;
  const stack = columnStack({ column: undated, cx, barWidth, bottom, yOf, active });
  return html`${linked(undated.href, html`<rect class="hit" x="${cx - 12}" y="${Math.min(yOf(stack.total), bottom - 24)}" width="24" height="${bottom - Math.min(yOf(stack.total), bottom - 24)}" />${stack.outline}${stack.marks}`, [`${stack.total} élément${stack.total > 1 ? "s" : ""}`, "Non daté"])}
    ${axisText(cx, bottom + 18, "Non daté")}
    <path
      class="axis-break"
      d="M${left + undatedWidth - 12},${bottom + 4} l4,-8 M${left + undatedWidth - 6},${bottom + 4} l4,-8"
    />`;
}

export function ownerBars({ width, rows }) {
  const labelWidth = Math.min(180, width * 0.3);
  const rowHeight = 26;
  const right = 36;
  const max = Math.max(1, ...rows.map((row) => row.total));
  const xOf = scale(0, max, 0, width - labelWidth - right);
  const height = rows.length * rowHeight + 4;
  return frame(
    width,
    height,
    "Actions ouvertes par responsable",
    rows.map((row, index) => {
      const y = index * rowHeight + 4;
      const barHeight = 16;
      return html`${axisText(labelWidth - 8, y + barHeight / 2 + 4, truncate(row.label, 26), "end")}
      ${stackedHBar({ y, segments: row.segments, x0: labelWidth, xOf: (amount) => labelWidth + xOf(amount), height: barHeight, href: row.href, totalLabel: String(row.total) })}`;
    }),
  );
}

export function dumbbellChart({ width, rows, start, end }) {
  const labelWidth = Math.min(380, width * 0.42);
  const rowHeight = 28;
  const top = 8;
  const height = top + rows.length * rowHeight + 24;
  const total = Math.max(1, daysBetween(start, end));
  const xOf = (day) => labelWidth + 12 + (daysBetween(start, day) / total) * (width - labelWidth - 28);
  const ticks = monthTicks(start, total + 1).filter((tick) => tick.day.endsWith("-01"));
  return frame(
    width,
    height,
    "Proposition puis décision",
    html`${ticks.map((tick) => html`${gridLine(xOf(tick.day), top, xOf(tick.day), height - 22)}${axisText(xOf(tick.day), height - 6, formatDay(tick.day, { year: false }))}`)}
    ${rows.map((row, index) => dumbbellRow(row, top + index * rowHeight + rowHeight / 2, xOf))}`,
  );
}

function dumbbellRow(row, cy, xOf) {
  const decided = row.decidedRange.map(xOf);
  const proposed = row.proposedDay ? xOf(row.proposedDay) : null;
  const from = proposed ?? decided[0];
  const tone = row.current ? "is-current" : "is-past";
  return linked(
    row.href,
    html`<text class="axis-text is-ink" x="0" y="${cy + 4}">${row.id}</text>
      <text class="axis-text" x="52" y="${cy + 4}">${truncate(row.statement, 48)}</text>
      ${from != null ? html`<line class="dumbbell-line ${tone}" x1="${from}" y1="${cy}" x2="${decided[decided.length - 1]}" y2="${cy}" />` : ""}
      ${proposed != null ? html`<circle class="dumbbell-open ${tone}" cx="${proposed}" cy="${cy}" r="5" />` : ""}
      ${decided.map((cx) => html`<circle class="dumbbell-filled ${tone}" cx="${cx}" cy="${cy}" r="5" />`)}`,
    [row.id, `Proposée : ${row.proposedLabel}`, `Décidée : ${row.decidedLabel}`, row.status],
  );
}
