import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { KINDS, useUnits } from "./units.jsx";

/** A small "?" that shows `text` on hover. */
export function Help({ text }) {
  if (!text) return null;
  return (
    <span className="help" title={text} aria-label={text}>
      ?
    </span>
  );
}

/** A label, optional help text, and the control under it. */
export function Field({ label, help, children, className = "" }) {
  return (
    <label className={`field ${className}`}>
      {label && (
        <span className="field-label">
          {label}
          <Help text={help} />
        </span>
      )}
      {children}
    </label>
  );
}

const decimalsOf = (step) => (String(step).split(".")[1] || "").length;

/**
 * A number box that lets you clear it (value null) and type freely.
 * `decimals` fixes how it is shown when you leave the box. `stepper` adds −/+ buttons.
 */
export function NumInput({
  value, onChange, onCommit, step = 1, min, max, decimals, placeholder, readOnly, stepper = false, className = "", ...rest
}) {
  const show = (v) => (v == null ? "" : decimals != null ? Number(v).toFixed(decimals) : String(v));
  const [text, setText] = useState(show(value));

  // Follow outside changes (loading a recipe, a calculated field) but not our own typing ("1." stays "1.").
  useEffect(() => {
    const parsed = text.trim() === "" ? null : Number(text);
    if (parsed !== value) setText(show(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const clamp = (n) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, n));

  function type(raw) {
    setText(raw);
    if (raw.trim() === "") return onChange(null);
    const n = Number(raw);
    if (Number.isFinite(n)) onChange(n);
  }

  function nudge(dir) {
    const digits = Math.max(decimalsOf(step), decimals ?? 0);
    const next = clamp(Number(((value ?? 0) + dir * step).toFixed(digits)));
    setText(show(next));
    onChange(next);
    onCommit?.();
  }

  function leave() {
    if (text.trim() === "") (setText(""), onCommit?.());
    else {
      const n = Number(text);
      if (!Number.isFinite(n)) setText(show(value));
      else {
        const c = clamp(n);
        if (c !== n) onChange(c);
        setText(show(c));
      }
      onCommit?.();
    }
  }

  return (
    <span className={`num ${className}`}>
      <input
        type="text"
        inputMode="decimal"
        value={text}
        placeholder={placeholder}
        readOnly={readOnly}
        onChange={(e) => type(e.target.value)}
        onBlur={leave}
        onKeyDown={(e) => {
          if (readOnly) return;
          if (e.key === "ArrowUp") (e.preventDefault(), nudge(1));
          if (e.key === "ArrowDown") (e.preventDefault(), nudge(-1));
        }}
        {...rest}
      />
      {stepper && !readOnly && (
        <>
          <button type="button" tabIndex={-1} className="step" aria-label="Decrease" onClick={() => nudge(-1)}>
            −
          </button>
          <button type="button" tabIndex={-1} className="step" aria-label="Increase" onClick={() => nudge(1)}>
            +
          </button>
        </>
      )}
    </span>
  );
}

/**
 * A NumInput for a quantity with units. `value`, `onChange`, `step`, `min`, `max` and `decimals` are all in imperial
 * (what is stored); in metric mode the box shows and accepts metric and converts back, with its own step and decimals.
 */
export function UnitNum({ kind, value, onChange, step, min, max, decimals, ...rest }) {
  const { metric } = useUnits();
  if (!metric) return <NumInput key="imperial" value={value} onChange={onChange} step={step} min={min} max={max} decimals={decimals} {...rest} />;
  const k = KINDS[kind];
  return (
    <NumInput
      key="metric"
      {...rest}
      value={value == null ? null : Number(k.to(value).toFixed(6))}
      onChange={(v) => onChange(v == null ? null : k.from(v))}
      step={k.step}
      decimals={k.dec}
      min={min == null ? undefined : k.to(min)}
      max={max == null ? undefined : k.to(max)}
    />
  );
}

/**
 * A searchable drop-down. options: [{ value, label, group? }]. Options with a `group` are listed under group
 * headings (keep them sorted by group), and typing also matches the group name. A value that is not in the list
 * (an ingredient the reference no longer has) is still shown, marked as unknown.
 */
export function Combobox({ options, value, onChange, placeholder = "Choose…", clearable = false, className = "" }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(null); // null = show the chosen item, string = the user is typing
  const [hi, setHi] = useState(0);
  const [rect, setRect] = useState(null);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  const selected = options.find((o) => o.value === value);
  const unknown = Boolean(value) && !selected;
  const q = (query ?? "").trim().toLowerCase();
  const filtered = useMemo(
    () => (q ? options.filter((o) => `${o.label} ${o.group || ""}`.toLowerCase().includes(q)) : options).slice(0, 200),
    [options, q],
  );

  // The list is positioned in fixed coordinates so scrolling tables don't clip it.
  useLayoutEffect(() => {
    if (!open) return undefined;
    const place = () => inputRef.current && setRect(inputRef.current.getBoundingClientRect());
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open]);

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-i="${hi}"]`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }, [hi, open]);

  function choose(o) {
    onChange(o.value);
    setOpen(false);
    setQuery(null);
    inputRef.current?.blur();
  }

  function onKeyDown(e) {
    if (e.key === "ArrowDown") (e.preventDefault(), setOpen(true), setHi((h) => Math.min(h + 1, filtered.length - 1)));
    else if (e.key === "ArrowUp") (e.preventDefault(), setHi((h) => Math.max(h - 1, 0)));
    else if (e.key === "Enter" && open && filtered[hi]) (e.preventDefault(), choose(filtered[hi]));
    else if (e.key === "Escape") (setOpen(false), setQuery(null), inputRef.current?.blur());
  }

  const text = open && query !== null ? query : selected ? selected.label : value || "";
  return (
    <span className={`combo ${unknown ? "unknown" : ""} ${className}`}>
      <input
        ref={inputRef}
        type="text"
        value={text}
        placeholder={placeholder}
        title={unknown ? "Not in the reference list" : undefined}
        onFocus={(e) => {
          setQuery(null);
          setHi(Math.max(0, options.findIndex((o) => o.value === value)));
          setOpen(true);
          requestAnimationFrame(() => e.target.select());
        }}
        onBlur={() => (setOpen(false), setQuery(null))}
        onChange={(e) => (setQuery(e.target.value), setHi(0), setOpen(true))}
        onKeyDown={onKeyDown}
      />
      {clearable && value ? (
        <button type="button" tabIndex={-1} className="clear" aria-label="Clear" onMouseDown={(e) => e.preventDefault()} onClick={() => onChange("")}>
          ×
        </button>
      ) : (
        <span className="caret" aria-hidden="true">▾</span>
      )}
      {open && rect && (
        <ul
          ref={listRef}
          className="combo-list"
          style={{ left: rect.left, top: rect.bottom + 2, minWidth: rect.width, maxHeight: Math.max(160, window.innerHeight - rect.bottom - 16) }}
        >
          {filtered.length === 0 && <li className="none">No matches</li>}
          {filtered.map((o, i) => [
            o.group && o.group !== filtered[i - 1]?.group && (
              <li key={`g-${o.group}`} className="group" onMouseDown={(e) => e.preventDefault()}>
                {o.group}
              </li>
            ),
            <li
              key={o.value + i}
              data-i={i}
              className={`${i === hi ? "hi" : ""} ${o.value === value ? "chosen" : ""}`}
              onMouseDown={(e) => (e.preventDefault(), choose(o))}
              onMouseEnter={() => setHi(i)}
            >
              {o.label}
            </li>,
          ])}
        </ul>
      )}
    </span>
  );
}

/** A big number with a small label, like Streamlit's metric. */
export function Metric({ label, value, help, delta, deltaTone = "normal", className = "" }) {
  let tone = "";
  if (delta) {
    const up = !delta.startsWith("-");
    tone = (deltaTone === "inverse" ? !up : up) ? "good" : "bad";
  }
  return (
    <div className={`metric ${className}`}>
      <div className="metric-label">
        {label}
        <Help text={help} />
      </div>
      <div className="metric-value">{value}</div>
      {delta && <div className={`metric-delta ${tone}`}>{delta}</div>}
    </div>
  );
}

export const Banner = ({ kind = "info", children }) => <div className={`banner ${kind}`}>{children}</div>;

/** A collapsible section. */
export function Expander({ title, defaultOpen = false, children }) {
  return (
    <details className="expander" open={defaultOpen}>
      <summary>{title}</summary>
      <div className="expander-body">{children}</div>
    </details>
  );
}
