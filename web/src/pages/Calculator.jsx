import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api.js";
import Glass from "../Glass.jsx";
import { Banner, Combobox, Expander, Field, Help, Metric, NumInput, UnitNum } from "../components.jsx";
import { fixed, g, rangeStatus } from "../format.js";
import { useUnits } from "../units.jsx";

const blankGrain = () => ({ name: "", lbs: 1.0 });
const blankAddition = () => ({ name: "", amount: "", unit: "", notes: "" });
// A hop line's time is minutes for every use except dry hop, which is days. When switching between the two,
// start from a sensible time for the new use rather than carrying over (say) 60 "days".
const DEFAULT_TIME = { boil: 60, "first wort": 60, flameout: 0, whirlpool: 15, "dry hop": 3 };
// Hop lines are kept in the order they go into the kettle: by use, then by time (longest first).
const USE_ORDER = ["first wort", "boil", "flameout", "whirlpool", "dry hop"];
const useRank = (use) => (USE_ORDER.indexOf(use) === -1 ? USE_ORDER.length : USE_ORDER.indexOf(use));
const sortHops = (hops) =>
  hops
    .map((h, i) => ({ h, i }))
    .sort((a, b) => useRank(a.h.use) - useRank(b.h.use) || (b.h.minutes ?? 0) - (a.h.minutes ?? 0) || a.i - b.i)
    .map((x) => x.h);

// Sparge water goes in at 170 °F (not part of the calculation).
const SPARGE_TEMP_F = 170;
// Rest lengths shown in the mash table (not part of the calculation): the main mash and each infusion step.
const MASH_MINUTES = 60;
const INFUSION_MINUTES = 10;

const blankHop = () => ({ name: "", oz: 1.0, form: "pellet", use: "boil", minutes: 60, alpha_acid: null, notes: "" });

/** Sends the recipe to the server (shortly after you stop typing) and returns the latest numbers. */
function useCalculation(recipe) {
  const [state, setState] = useState({ result: null, error: null });
  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      api
        .post("/api/calculate", recipe, ctrl.signal)
        .then((result) => setState({ result, error: null }))
        // Keep showing the last good numbers next to the error message.
        .catch((e) => e.name !== "AbortError" && setState((s) => ({ ...s, error: e.message })));
    }, 120);
    return () => (clearTimeout(t), ctrl.abort());
  }, [recipe]);
  return state;
}

export default function Calculator({ recipe, setRecipe, reference, onSave, unsaved, isNew }) {
  const { result, error } = useCalculation(recipe);
  const set = (patch) => setRecipe((r) => ({ ...r, ...patch }));
  const setBatch = (patch) => setRecipe((r) => ({ ...r, batch: { ...r.batch, ...patch } }));
  const setMash = (patch) => setRecipe((r) => ({ ...r, mash: { ...r.mash, ...patch } }));

  const grainOptions = useMemo(() => {
    const order = ["Grain", "Extract", "Sugar", "Fruit", "Other"];
    const rank = (x) => (order.indexOf(x.category) + 1 || order.length + 1);
    const types = ["Base malt", "Kilned malt", "Crystal malt", "Specialty malt", "Roasted malt", "Smoked malt", "Acidulated malt", "Adjunct grain"];
    const typeRank = (x) => (types.indexOf(x.type) + 1 || types.length + 1);
    return [...reference.grains]
      .sort((a, b) => rank(a) - rank(b) || typeRank(a) - typeRank(b) || (a.type || "").localeCompare(b.type || "") || a.name.localeCompare(b.name))
      .map((x) => ({ value: x.name, label: x.name, group: x.category ? `${x.category} · ${x.type}` : undefined }));
  }, [reference]);
  const hopOptions = useMemo(() => reference.hops.map((x) => ({ value: x.name, label: x.name })), [reference]);
  const yeastOptions = useMemo(() => reference.yeasts.map((x) => ({ value: x.name, label: x.display })), [reference]);
  const styleOptions = useMemo(() => reference.styles.map((x) => ({ value: x.name, label: x.name })), [reference]);
  const baseOptions = useMemo(
    () => reference.styles.filter((x) => x.og && !x.name.startsWith("34")).map((x) => ({ value: x.name, label: x.name })),
    [reference],
  );
  const yeast = reference.yeasts.find((y) => y.name === recipe.yeast);

  return (
    <>
      <h1 className="brand-title">Henske Brewing Calculator</h1>

      <div className="row two-one">
        <Field label="Recipe name">
          <input className="input" value={recipe.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label="Style">
          <Combobox
            options={styleOptions}
            value={recipe.style}
            onChange={(v) => set({ style: v })}
            placeholder="Choose a style"
            clearable
          />
        </Field>
      </div>

      <StyleInfo style={result?.style_target} />
      {result?.style_target?.needs_base && (
        <Field label="Base beer style" help="This style's ranges depend on the underlying beer. Pick the base style to use its target ranges.">
          <Combobox options={baseOptions} value={recipe.base_style} onChange={(v) => set({ base_style: v })} placeholder="Choose a base style" clearable />
        </Field>
      )}

      <StatsBox result={result} error={error} onSave={onSave} unsaved={unsaved} isNew={isNew} />

      <SystemSpecs recipe={recipe} setBatch={setBatch} />

      <GrainBill recipe={recipe} set={set} options={grainOptions} result={result} />
      <Hops recipe={recipe} set={set} options={hopOptions} reference={reference} result={result} />
      <Additions recipe={recipe} set={set} />
      <Yeast recipe={recipe} set={set} options={yeastOptions} yeast={yeast} />
      <Mash recipe={recipe} set={set} setMash={setMash} result={result} />

      <Field label="Recipe notes">
        <textarea className="input" rows={4} value={recipe.notes} onChange={(e) => set({ notes: e.target.value })} />
      </Field>
    </>
  );
}

/** The selected style's BJCP overall impression and characteristic ingredients. */
function StyleInfo({ style }) {
  const info = style?.info;
  if (!info || !(info["Overall Impression"] || info["Characteristic Ingredients"])) return null;
  return (
    <div className="style-info">
      {info["Overall Impression"] && (
        <p>
          <strong>Overall impression.</strong> {info["Overall Impression"]}
        </p>
      )}
      {info["Characteristic Ingredients"] && (
        <p>
          <strong>Characteristic ingredients.</strong> {info["Characteristic Ingredients"]}
        </p>
      )}
      <span className="style-info-source">BJCP 2021 · {style.name}</span>
    </div>
  );
}

// --------------------------------------------------------------------------
// Stats box (pinned to the top while you scroll)
// --------------------------------------------------------------------------

function StatsBox({ result: r, error, onSave, unsaved, isNew }) {
  const t = r?.style_target;
  // Each tile's value and its style range share a colour: green inside the range, amber a little outside, red further out.
  const status = (value, key, digits) => (r ? rangeStatus(value, t?.[key], digits) : { text: "", tone: "" });
  return (
    <div className="stats-sticky">
      {error && <Banner kind="error">{error}</Banner>}
      <div className="stats">
        <Tile col={1} label="OG" value={r ? fixed(r.og, 3) : "–"} {...status(r?.og, "og", 3)} />
        <Tile col={2} label="FG" value={r ? fixed(r.fg, 3) : "–"} {...status(r?.fg, "fg", 3)} help={r && `${g(r.attenuation_pct)}% attenuation`} />
        <Tile
          col={3}
          label="ABV"
          value={r ? `${fixed(r.abv, 1)}%` : "–"}
          {...status(r?.abv, "abv")}
          help={r && `Alternate formula: ${fixed(r.abv_alternate, 2)}%`}
        />
        <Tile col={4} label="IBU" value={r ? fixed(r.ibu, 0) : "–"} {...status(r?.ibu, "ibu")} help="Tinseth" />
        <Tile
          col={5}
          label="SRM"
          value={r ? fixed(r.srm, 1) : "–"}
          aside={r && `(${r.srm_color_name})`}
          {...status(r?.srm, "srm")}
          help="Morey"
        />
        <div className="tile glass">{r && <Glass hex={r.srm_hex} label={r.srm_color_name} />}</div>
        <div className="tile save">
          <button className={unsaved ? "primary" : ""} disabled={!unsaved} onClick={onSave}>
            Save
          </button>
          <span className="save-state">{unsaved ? (isNew ? "Not saved yet" : "Unsaved changes") : "Saved"}</span>
        </div>
        {t && ["abv", "ibu", "og", "fg", "srm"].some((k) => t[k]) && <div className="stats-title">{t.name}{t.base ? ` (base: ${t.base})` : ""} Target Ranges</div>}
      </div>
    </div>
  );
}

function Tile({ col, label, value, aside, text, tone, help }) {
  return (
    <div className={`tile c${col} ${tone}`}>
      <div className="tile-label">
        {label}
        <Help text={help} />
      </div>
      <div className="tile-value">
        {value}
        {aside && <span className="tile-aside">{aside}</span>}
      </div>
      <div className="tile-note">{text || " "}</div>
    </div>
  );
}

// --------------------------------------------------------------------------
// System specifications
// --------------------------------------------------------------------------

function SystemSpecs({ recipe, setBatch }) {
  const u = useUnits();
  const b = recipe.batch;
  // The recipe stores the target batch volume (post_boil_gal) plus the
  // boil-off and trub losses; pre-boil is always the sum of the three.
  // (A recipe saved before the split has only the two volumes; its whole difference counts as boil-off.)
  const legacy = b.boil_off_gal == null && b.trub_loss_gal == null;
  const boilOff = legacy ? Math.max(0, b.pre_boil_gal - b.post_boil_gal) : b.boil_off_gal ?? 0;
  const trub = legacy ? 0 : b.trub_loss_gal ?? 0;
  const volumes = (post, off, tr) => ({
    post_boil_gal: post,
    boil_off_gal: off,
    trub_loss_gal: tr,
    pre_boil_gal: post + off + tr,
  });
  return (
    <section>
      <h2>System Specifications</h2>
      <div className="row five aligned">
        <Field
          label={`Target batch volume (${u.label("gal")})`}
          help="The volume you want in the fermenter. OG, IBU and color are calculated at this volume plus the trub loss (the wort volume at the end of the boil)."
        >
          <UnitNum
            kind="gal"
            stepper
            step={0.25}
            min={0}
            max={100}
            decimals={2}
            value={b.post_boil_gal}
            onChange={(v) => setBatch(volumes(v ?? 0, boilOff, trub))}
          />
        </Field>
        <Field label={`Boil-off volume loss (${u.label("gal")})`} help="Water lost to evaporation during the boil.">
          <UnitNum
            kind="gal"
            stepper
            step={0.25}
            min={0}
            max={100}
            decimals={2}
            value={boilOff}
            onChange={(v) => setBatch(volumes(b.post_boil_gal, v ?? 0, trub))}
          />
        </Field>
        <Field label={`Trub volume loss (${u.label("gal")})`} help="Wort left behind in the kettle with the trub. It is lost after the boil, so it adds to the volume OG is worked out at but not to the sugar concentration.">
          <UnitNum
            kind="gal"
            stepper
            step={0.25}
            min={0}
            max={100}
            decimals={2}
            value={trub}
            onChange={(v) => setBatch(volumes(b.post_boil_gal, boilOff, v ?? 0))}
          />
        </Field>
        <Field label={`Pre-boil volume (${u.label("gal")})`} help="Calculated: target batch volume + boil-off + trub loss.">
          <UnitNum kind="gal" readOnly decimals={2} value={b.pre_boil_gal} onChange={() => {}} />
        </Field>
        <Field label="Mash efficiency (%)">
          <NumInput
            stepper
            step={1}
            min={0}
            max={100}
            value={b.efficiency_pct}
            onChange={(v) => setBatch({ efficiency_pct: v ?? 0 })}
          />
        </Field>
      </div>
    </section>
  );
}

// --------------------------------------------------------------------------
// Grain bill
// --------------------------------------------------------------------------

function GrainBill({ recipe, set, options, result }) {
  const u = useUnits();
  const grains = recipe.grains;
  const edit = (i, patch) => set({ grains: grains.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  const rows = result?.grain_rows;
  return (
    <section>
      <h2>Grain bill</h2>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th className="w-name">Grain</th>
              <th className="w-num r">Amount ({u.label("lb")})</th>
              <th className="w-bar">%</th>
              <th className="w-sm r">PPG</th>
              <th className="w-md r">OG points</th>
              <th className="w-md r">Lovibond</th>
              <th className="w-sm r">MCU</th>
              <th className="w-x" />
            </tr>
          </thead>
          <tbody>
            {grains.map((gr, i) => {
              const row = rows && rows.length === grains.length ? rows[i] : null;
              return (
                <tr key={i}>
                  <td>
                    <Combobox options={options} value={gr.name} onChange={(v) => edit(i, { name: v })} placeholder="Choose a grain" />
                  </td>
                  <td>
                    <UnitNum kind="lb" step={0.25} min={0} decimals={2} value={gr.lbs} onChange={(v) => edit(i, { lbs: v })} />
                  </td>
                  <td className="calc">
                    {row ? (
                      <span className="bar">
                        <span className="bar-track">
                          <span className="bar-fill" style={{ width: `${Math.min(100, row.pct)}%` }} />
                        </span>
                        <span className="bar-text">{fixed(row.pct, 1)}%</span>
                      </span>
                    ) : null}
                  </td>
                  <td className="calc">{row ? g(row.ppg) : ""}</td>
                  <td className="calc">{row ? fixed(row.og_points, 1) : ""}</td>
                  <td className="calc">{row ? g(row.lovibond) : ""}</td>
                  <td className="calc">{row ? fixed(row.mcu, 2) : ""}</td>
                  <td>
                    <button className="icon" title="Remove this grain" onClick={() => set({ grains: grains.filter((_, j) => j !== i) })}>
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <button className="add" onClick={() => set({ grains: [...grains, blankGrain()] })}>
        + Add grain
      </button>
      {result && grains.length > 0 && (
        <p className="caption">
          Total {u.show("lb", result.total_grain_lbs)} · max {u.show("ppg", result.max_points_per_gal, 1)} pre-boil at 100%
        </p>
      )}
      {result?.unknown_grains.length > 0 && (
        <Banner kind="warning">Not in the grain reference, so left out: {result.unknown_grains.join(", ")}</Banner>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Other additions (free text; no reference data, no effect on the calculations)
// --------------------------------------------------------------------------

function Additions({ recipe, set }) {
  const items = recipe.additions || [];
  const edit = (i, patch) => set({ additions: items.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  return (
    <section>
      <h2>
        Other Additions
        <Help text="For additions that don't contribute to specific gravity or color" />
      </h2>
      {items.length > 0 && (
        <div className="table-wrap">
          <table className="grid additions">
            <thead>
              <tr>
                <th className="w-name">Ingredient</th>
                <th className="w-num">Amount</th>
                <th className="w-md">Unit</th>
                <th>Notes</th>
                <th className="w-x" />
              </tr>
            </thead>
            <tbody>
              {items.map((a, i) => (
                <tr key={i}>
                  <td>
                    <input className="input" value={a.name ?? ""} onChange={(e) => edit(i, { name: e.target.value })} aria-label="Ingredient" />
                  </td>
                  <td>
                    <input className="input" value={a.amount ?? ""} onChange={(e) => edit(i, { amount: e.target.value })} aria-label="Amount" />
                  </td>
                  <td>
                    <input className="input" value={a.unit ?? ""} onChange={(e) => edit(i, { unit: e.target.value })} aria-label="Unit" />
                  </td>
                  <td>
                    <input className="input" value={a.notes ?? ""} onChange={(e) => edit(i, { notes: e.target.value })} aria-label="Notes" />
                  </td>
                  <td>
                    <button className="icon" title="Remove this addition" onClick={() => set({ additions: items.filter((_, j) => j !== i) })}>
                      ×
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button className="add" onClick={() => set({ additions: [...items, blankAddition()] })}>
        + Add addition
      </button>
    </section>
  );
}

// --------------------------------------------------------------------------
// Hops
// --------------------------------------------------------------------------

function Hops({ recipe, set, options, reference, result }) {
  const u = useUnits();
  const hopAA = useMemo(() => new Map(reference.hops.map((x) => [x.name, x.alpha_acid])), [reference]);
  const hops = recipe.hops;
  const refAA = (name) => hopAA.get(name) ?? null;
  const unitOf = (use) => reference.hop_time_units?.[use] ?? (use === "dry hop" ? "days" : "min");
  // Re-sort after a time is committed (box left, or - / + pressed). Waiting for the next render means the new
  // value is already in `hops`.
  const [sortTick, setSortTick] = useState(0);
  useEffect(() => {
    if (sortTick === 0) return;
    const sorted = sortHops(hops);
    if (sorted.some((h, i) => h !== hops[i])) set({ hops: sorted });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortTick]);
  const setUse = (i, use) => {
    const was = unitOf(hops[i].use);
    const patch = { use, ...(was !== unitOf(use) ? { minutes: DEFAULT_TIME[use] ?? 0 } : {}) };
    set({ hops: sortHops(hops.map((x, j) => (j === i ? { ...x, ...patch } : x))) });
  };
  const edit = (i, patch) => set({ hops: hops.map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  const rows = result?.hop_rows && result.hop_rows.length === hops.length ? result.hop_rows : null;
  return (
    <section>
      <h2>Hops</h2>
      <div className="table-wrap">
        <table className="grid hops">
          <thead>
            <tr>
              <th className="w-name">Hop</th>
              <th className="w-num r">Amount ({u.label("oz")})</th>
              <th className="w-form">Form</th>
              <th className="w-use">Use</th>
              <th className="w-time r" title="Minutes, or days for a dry hop">Time</th>
              <th className="w-aa r">
                AA %
                <Help text="Populated from reference data, manually override for actual lot AA%" />
              </th>
              <th className="w-calc r" title="Tinseth utilization for this addition (first wort counts 10% extra)">
                Utilization
              </th>
              <th className="w-calc r">IBU</th>
              <th className="w-x" />
            </tr>
          </thead>
          <tbody>
            {hops.map((h, i) => (
              <tr key={i}>
                <td>
                  <Combobox options={options} value={h.name} onChange={(v) => edit(i, { name: v })} placeholder="Choose a hop" />
                </td>
                <td>
                  <UnitNum kind="oz" step={0.25} min={0} decimals={2} value={h.oz} onChange={(v) => edit(i, { oz: v })} />
                </td>
                <td>
                  <select className="input" value={h.form} onChange={(e) => edit(i, { form: e.target.value })}>
                    {reference.hop_forms.map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select className="input" value={h.use} onChange={(e) => setUse(i, e.target.value)}>
                    {reference.hop_uses.map((u) => (
                      <option key={u}>{u}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <span className="with-unit">
                    <NumInput step={1} min={0} value={h.minutes} onChange={(v) => edit(i, { minutes: v })} onCommit={() => setSortTick((t) => t + 1)} />
                    <span className="unit">{unitOf(h.use)}</span>
                  </span>
                </td>
                <td className={h.alpha_acid != null && h.alpha_acid !== refAA(h.name) ? "overridden" : ""}>
                  {/* Shows the reference average until you type your own. The recipe only stores your number
                      (blank means "use the reference"), so clearing the box or retyping the reference value resets it. */}
                  <NumInput
                    step={0.1}
                    min={0}
                    max={30}
                    decimals={1}
                    placeholder="–"
                    title={
                      h.alpha_acid != null && h.alpha_acid !== refAA(h.name)
                        ? `Your value (reference average: ${refAA(h.name) ?? "none"})`
                        : undefined
                    }
                    value={h.alpha_acid ?? refAA(h.name)}
                    onChange={(v) => edit(i, { alpha_acid: v == null || v === refAA(h.name) ? null : v })}
                  />
                </td>
                <td className="calc">{rows?.[i] ? fixed(rows[i].utilization, 3) : ""}</td>
                <td className="calc">{rows?.[i] ? fixed(rows[i].ibu, 1) : ""}</td>
                <td>
                  <button className="icon" title="Remove this hop" onClick={() => set({ hops: hops.filter((_, j) => j !== i) })}>
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="add" onClick={() => set({ hops: [...hops, blankHop()] })}>
        + Add hop
      </button>

      {result?.missing_hops.length > 0 && (
        <Banner kind="warning">No reference alpha acid for {result.missing_hops.join(", ")}; enter the AA %.</Banner>
      )}
    </section>
  );
}

// --------------------------------------------------------------------------
// Yeast
// --------------------------------------------------------------------------

function Yeast({ recipe, set, options, yeast }) {
  const u = useUnits();
  return (
    <section>
      <h2>Yeast</h2>
      <Combobox options={options} value={recipe.yeast} onChange={(v) => set({ yeast: v })} placeholder="Choose a yeast" clearable />
      <div className="row yeast-stats">
        <Metric
          label="Attenuation"
          value={yeast ? `${g(yeast.attenuation)}%` : "–"}
          help={yeast?.attenuation_range ? `Range ${yeast.attenuation_range}` : undefined}
        />
        <Field label="Attenuation Override" help="Input your own attenuation value if you have different data for your yeast">
          <NumInput
            stepper
            step={0.5}
            min={0}
            max={100}
            placeholder="%"
            value={recipe.attenuation_pct || null}
            onChange={(v) => set({ attenuation_pct: v || null })}
          />
        </Field>
        <Metric label="Flocculation" value={yeast?.flocculation || "–"} />
        <Metric label="Temp range" value={u.tempRange(yeast?.temp_range_f)} />
        <Metric label="Type" value={yeast?.type || "–"} help={yeast ? `${yeast.lab} · ${yeast.form}` : undefined} />
      </div>
      {yeast?.notes && <p className="caption">{yeast.notes}</p>}
    </section>
  );
}

// --------------------------------------------------------------------------
// Mash
// --------------------------------------------------------------------------

const DEFAULT_DECOCTION_STEPS = [
  { name: "Protein rest", temp_f: 131, minutes: 20 },
  { name: "Saccharification", temp_f: 152, minutes: 60 },
  { name: "Mash out", temp_f: 170, minutes: 10 },
];

function Mash({ recipe, set, setMash, result }) {
  const u = useUnits();
  const m = recipe.mash;
  const mashType = recipe.mash_type === "decoction" ? "decoction" : "basic";
  const decSteps = recipe.decoction_steps ?? DEFAULT_DECOCTION_STEPS;
  const setDecSteps = (steps) => set({ decoction_steps: steps });
  const editStep = (i, patch) => setDecSteps(decSteps.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  // The step temperatures are typed as text ("170, 175"); keep what was typed and store the numbers.
  // The text is in the displayed unit; the recipe keeps °F. Switching units rewrites the text from the stored values.
  const stepsAsText = () => (m.step_temps_f || []).map((f) => g(Number(u.toShown("temp", f).toFixed(1)))).join(", ");
  const [stepsText, setStepsText] = useState(stepsAsText);
  const firstRun = useRef(true);
  useEffect(() => {
    if (firstRun.current) firstRun.current = false;
    else setStepsText(stepsAsText());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [u.system]);
  const parts = stepsText.replace(/;/g, ",").split(",").map((p) => p.trim()).filter(Boolean);
  const bad = parts.filter((p) => !Number.isFinite(Number(p)));

  // `kind` marks a field with units; its props (step, min, max, decimals) are the imperial ones.
  const num = (key, props, kind) =>
    kind ? (
      <UnitNum kind={kind} value={m[key]} onChange={(v) => setMash({ [key]: v ?? 0 })} {...props} />
    ) : (
      <NumInput value={m[key]} onChange={(v) => setMash({ [key]: v ?? 0 })} {...props} />
    );
  const infusions = result?.infusions ?? [];
  const dec = result?.decoction;
  // One row per water addition. Basic: strike, then each boiling-water infusion (the last is the mash-out), then
  // sparge. Decoction: strike for the first rest, then each later rest (reached by a decoction pull), then sparge.
  const sparge = { name: "Sparge", temp: SPARGE_TEMP_F, gal: result?.sparge_water_gal, target: SPARGE_TEMP_F, minutes: null };
  let stepRows = [];
  if (result && mashType === "basic") {
    stepRows = [
      { name: "Strike", temp: result.strike_water_temp_f, gal: result.strike_water_qt / 4, target: m.mash_temp_f, minutes: MASH_MINUTES },
      ...infusions.map((s, i) => ({
        name: i === infusions.length - 1 ? "Mash Out" : `Step ${i + 1}`,
        temp: m.boiling_water_temp_f,
        gal: s.boiling_water_qt / 4,
        target: s.target_temp_f,
        minutes: INFUSION_MINUTES,
        note: `Assumes the mash has cooled to ${u.show("temp", s.start_temp_f)} first`,
      })),
      sparge,
    ];
  } else if (result && dec) {
    stepRows = [
      ...dec.steps.map((s, i) =>
        i === 0
          ? {
              name: s.name ? `Strike (${s.name})` : "Strike",
              temp: dec.strike_water_temp_f,
              gal: dec.strike_water_qt / 4,
              target: s.target_temp_f,
              minutes: s.minutes,
            }
          : {
              name: s.name || `Step ${i + 1}`,
              temp: null,
              gal: null,
              target: s.target_temp_f,
              minutes: s.minutes,
              pull: s.pull_qt > 0 ? s : null,
              note: `Assumes the mash has cooled to ${u.show("temp", Math.round(s.start_temp_f * 10) / 10)} first`,
            },
      ),
      { ...sparge, gal: dec.sparge_water_gal },
    ];
  }
  const decoctionMode = mashType === "decoction";

  return (
    <section>
      <div className="section-head">
        <h2>Mash</h2>
        <div className="seg" role="group" aria-label="Mash type">
          {[
            ["basic", "Basic mash"],
            ["decoction", "Decoction mash"],
          ].map(([key, label]) => (
            <button key={key} type="button" className={mashType === key ? "on" : ""} aria-pressed={mashType === key} onClick={() => set({ mash_type: key })}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className={`row ${decoctionMode ? "two" : "three"}`}>
        <Field label={`Mash thickness (${u.label("qtlb")})`}>{num("thickness_qt_per_lb", { stepper: true, step: 0.05, min: 0.5, max: 4 }, "qtlb")}</Field>
        <Field label={`Grain temp (${u.label("temp")})`}>{num("grain_temp_f", { stepper: true, step: 1, min: 0, max: 120 }, "temp")}</Field>
        {!decoctionMode && <Field label={`Mash temp (${u.label("temp")})`}>{num("mash_temp_f", { stepper: true, step: 1, min: 100, max: 180 }, "temp")}</Field>}
      </div>
      {decoctionMode ? (
        <>
          <div className="table-wrap">
            <table className="grid">
              <thead>
                <tr>
                  <th>Rest</th>
                  <th className="r w-num">Target temp ({u.label("temp")})</th>
                  <th className="r w-num">Time (min)</th>
                  <th className="w-x" />
                </tr>
              </thead>
              <tbody>
                {decSteps.map((st, i) => (
                  <tr key={i}>
                    <td>
                      <input className="input" placeholder="Rest name" value={st.name ?? ""} onChange={(e) => editStep(i, { name: e.target.value })} />
                    </td>
                    <td>
                      <UnitNum kind="temp" step={1} min={80} max={175} value={st.temp_f} onChange={(v) => editStep(i, { temp_f: v })} />
                    </td>
                    <td>
                      <NumInput step={5} min={0} max={240} value={st.minutes} onChange={(v) => editStep(i, { minutes: v })} />
                    </td>
                    <td>
                      <button className="icon" title="Remove this rest" onClick={() => setDecSteps(decSteps.filter((_, j) => j !== i))}>
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button className="add" onClick={() => setDecSteps([...decSteps, { name: "", temp_f: 160, minutes: 15 }])}>
            + Add rest
          </button>
          <p className="caption">
            The first rest is the dough-in, so strike water is sized to land on it. Each later rest is reached by pulling a thick
            portion of the mash, boiling it and returning it.
          </p>
        </>
      ) : (
        <>
          <Field label={`Infusion step temps (${u.label("temp")})`} help={`Boiling-water infusions after the main rest, comma separated. E.g. ${u.metric ? 77 : 170} for a mash-out.`}>
            <input
              className="input"
              placeholder={u.metric ? "e.g. 77" : "e.g. 170"}
              value={stepsText}
              onChange={(e) => {
                setStepsText(e.target.value);
                const nums = e.target.value.replace(/;/g, ",").split(",").map((p) => p.trim()).filter(Boolean).map(Number);
                setMash({ step_temps_f: nums.filter(Number.isFinite).map((n) => u.toImperial("temp", n)) });
              }}
            />
          </Field>
          {bad.map((p) => (
            <Banner key={p} kind="warning">Ignoring step temperature “{p}”: not a number</Banner>
          ))}
        </>
      )}

      <Expander title="Equipment settings">
        <div className="row four">
          {!decoctionMode && <Field label={`Boiling water (${u.label("temp")})`}>{num("boiling_water_temp_f", { stepper: true, step: 1, min: 180, max: 212 }, "temp")}</Field>}
          <Field
            label={`Expected temperature drop during 60 minute mash (${u.label("dtemp")})`}
            help={decoctionMode ? "How much the mash cools over a 60 minute rest, before the next decoction pull." : "How much the mash cools during a rest before the next infusion."}
          >
            {num("rest_temp_loss_f", { stepper: true, step: 0.5, min: 0, max: 20 }, "dtemp")}
          </Field>
          <Field label={`Grain absorption (${u.label("gallb")})`}>
            {num("grain_absorption_gal_per_lb", { stepper: true, step: 0.005, min: 0, max: 0.3, decimals: 3 }, "gallb")}
          </Field>
          <Field label={`Mash tun deadspace (${u.label("gal")})`}>{num("mash_tun_deadspace_gal", { stepper: true, step: 0.05, min: 0, max: 5 }, "gal")}</Field>
        </div>
      </Expander>

      {result && stepRows.length > 0 && (
        <>
          <div className="table-wrap results">
            <table className="grid plain mash-steps">
              <thead>
                <tr>
                  <th>Step</th>
                  <th className="r">Water temperature</th>
                  <th className="r">Water volume</th>
                  <th className="r">Target mash temperature</th>
                  <th className="r">Time</th>
                  {decoctionMode && <th className="r" title="Thick mash pulled, boiled and returned to reach the target temperature">Decoction pull</th>}
                </tr>
              </thead>
              <tbody>
                {stepRows.map((r, i) => (
                  <tr key={i}>
                    <td title={r.note}>{r.name}</td>
                    <td className="r">{r.temp != null ? u.show("temp", r.temp, 1) : "–"}</td>
                    <td className="r">
                      {r.gal != null ? (
                        <>
                          {u.show("gal", r.gal, 2)} {!u.metric && <span className="unit">({fixed(r.gal * 4, 1)} qt)</span>}
                        </>
                      ) : (
                        "–"
                      )}
                    </td>
                    <td className="r">{r.target != null ? u.show("temp", r.target, 1) : "–"}</td>
                    <td className="r">{r.minutes != null ? `${r.minutes} min` : "–"}</td>
                    {decoctionMode && (
                      <td className="r">
                        {r.pull ? (
                          <>
                            {u.show("gal", r.pull.pull_qt / 4, 2)}{" "}
                            <span className="unit">({u.metric ? "" : `${fixed(r.pull.pull_qt, 1)} qt · `}{fixed(r.pull.pull_fraction * 100, 0)}%)</span>
                          </>
                        ) : (
                          "–"
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row two" style={{ marginTop: "1rem" }}>
            <Metric
              label="Target pre-boil specific gravity"
              value={fixed(result.pre_boil_gravity, 3)}
              help="Gravity of the wort in the kettle before the boil; a little lower than OG."
            />
          </div>
          {decoctionMode ? (
            <p className="caption">
              The pull is a share of the whole mash ({u.show("gal", dec.mash_volume_qt / 4, 2)} of water plus grain). Boil it, return
              it, and the mash lands on the target. It assumes the pulled portion is thick like the rest of the mash, that it
              boils at {u.show("temp", 212, 0)}, and that each rest cools by the temperature drop in Equipment settings (scaled to the rest time).
            </p>
          ) : (
            <p className="caption">
              Total water {u.show("gal", result.mash_water_gal + result.sparge_water_gal, 2)}: {u.show("gal", result.mash_water_gal, 2)} in the
              mash, {u.show("gal", result.absorbed_gal, 2)} absorbed by grain, the rest sparge. Each infusion assumes the mash has
              cooled by the temperature drop in Equipment settings.
            </p>
          )}
        </>
      )}
      {result && decoctionMode && !dec && <Banner kind="info">Add a rest with a target temperature to see the decoction schedule.</Banner>}
    </section>
  );
}
