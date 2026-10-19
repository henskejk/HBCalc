import { useEffect, useState } from "react";
import { api } from "../api.js";
import { Banner, Expander, Field, Metric, NumInput, UnitNum } from "../components.jsx";
import { fixed, g, signed } from "../format.js";
import { useUnits } from "../units.jsx";

/** The brew plan for the recipe snapshot, plus how the measurements compare. Refreshes as the log changes. */
function useBrewDay(log) {
  const [state, setState] = useState(null);
  const snapshot = log?.snapshot;
  const data = log?.data;
  useEffect(() => {
    if (!snapshot) return undefined;
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      api
        .post("/api/brewday", { recipe: snapshot, data }, ctrl.signal)
        .then((r) => setState({ result: r, error: null }))
        .catch((e) => e.name !== "AbortError" && setState((s) => ({ result: s?.result ?? null, error: e.message })));
    }, 120);
    return () => (clearTimeout(t), ctrl.abort());
  }, [snapshot, data]);
  return state ?? { result: null, error: null };
}

export default function BrewDay({ log, setLog, onSave, onDelete }) {
  const u = useUnits();
  const { result, error } = useBrewDay(log);

  if (!log) {
    return (
      <>
        <h1>Brew Day</h1>
        <Banner kind="info">Start a new log from the sidebar, or open a past one.</Banner>
      </>
    );
  }

  const d = log.data;
  const setData = (patch) => setLog((l) => ({ ...l, data: { ...l.data, ...patch } }));
  const readings = d.mash_readings;
  const editReading = (i, patch) => setData({ mash_readings: readings.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const plan = result?.plan;
  const actual = result?.actual;

  return (
    <>
      <h1>Brew Day</h1>
      <h2>
        {log.snapshot?.name}
        {log.snapshot?.style ? ` · ${log.snapshot.style}` : ""}
      </h2>
      {log.id == null && <p className="caption">Not saved yet</p>}
      {error && <Banner kind="error">{error}</Banner>}

      {plan && (
        <Expander title="Brew plan" defaultOpen={log.id == null}>
          <div className="row two">
            <div>
              <strong>Water</strong>
              <ul className="plain-list">
                <li>
                  Strike: <strong>{u.show("qt", plan.strike_water_qt, 1)}</strong> at <strong>{u.show("temp", plan.strike_water_temp_f, 1)}</strong>
                </li>
                <li>Mash at {u.show("temp", plan.mash_temp_f)}</li>
                {plan.infusions.map((s, i) => (
                  <li key={i}>
                    Add <strong>{u.show("qt", s.boiling_water_qt, 1)}</strong> boiling water → {u.show("temp", s.target_temp_f)}
                  </li>
                ))}
                <li>
                  Sparge: <strong>{u.show("gal", plan.sparge_water_gal, 2)}</strong>
                </li>
                <li>
                  Target pre-boil: {u.show("gal", plan.pre_boil_gal)} at {fixed(plan.pre_boil_gravity, 3)}
                </li>
              </ul>
              <strong>Grains</strong>
              {plan.grains.length ? (
                <ul className="plain-list">
                  {plan.grains.map((x, i) => (
                    <li key={i}>
                      {u.show("lb", x.lbs)} {x.name}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>–</p>
              )}
            </div>
            <div>
              <strong>Hops</strong>
              {plan.hops.length ? (
                <ul className="plain-list">
                  {plan.hops.map((h, i) => (
                    <li key={i}>
                      {h.use === "boil" ? `${g(h.minutes)} min` : h.minutes > 0 ? `${h.use} (${g(h.minutes)} ${h.time_unit})` : h.use}: {u.show("oz", h.oz)}{" "}
                      {h.name} ({g(h.alpha_acid)}% {h.form})
                    </li>
                  ))}
                </ul>
              ) : (
                <p>–</p>
              )}
              {plan.additions?.length > 0 && (
                <>
                  <strong>Other additions</strong>
                  <ul className="plain-list">
                    {plan.additions.map((a, i) => (
                      <li key={i}>
                        {[a.amount, a.unit].filter(Boolean).join(" ")} {a.name}
                        {a.notes ? ` (${a.notes})` : ""}
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <strong>Yeast</strong>
              <ul className="plain-list">
                <li>
                  {plan.yeast || "–"} ({g(plan.attenuation_pct)}% attenuation)
                </li>
              </ul>
            </div>
          </div>
        </Expander>
      )}

      <div className="row four">
        <Field label="Brew date">
          <input type="date" className="input" value={log.brew_date} onChange={(e) => setLog((l) => ({ ...l, brew_date: e.target.value }))} />
        </Field>
      </div>

      <h3>Mash temperature readings</h3>
      <div className="table-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th className="w-md" title="Clock time or minutes into the mash">
                Time
              </th>
              <th className="w-num">Temp ({u.label("temp")})</th>
              <th>Notes</th>
              <th className="w-x" />
            </tr>
          </thead>
          <tbody>
            {readings.map((r, i) => (
              <tr key={i}>
                <td>
                  <input className="input" value={r.time ?? ""} onChange={(e) => editReading(i, { time: e.target.value })} />
                </td>
                <td>
                  <UnitNum kind="temp" step={0.5} decimals={1} value={r.temp_f} onChange={(v) => editReading(i, { temp_f: v })} />
                </td>
                <td>
                  <input className="input" value={r.notes ?? ""} onChange={(e) => editReading(i, { notes: e.target.value })} />
                </td>
                <td>
                  <button className="icon" title="Remove this reading" onClick={() => setData({ mash_readings: readings.filter((_, j) => j !== i) })}>
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="add" onClick={() => setData({ mash_readings: [...readings, { time: "", temp_f: null, notes: "" }] })}>
        + Add reading
      </button>

      <h3>Gravity and volume</h3>
      <div className="row five">
        <Field label="Pre-boil SG">
          <NumInput stepper step={0.001} decimals={3} placeholder="–" value={d.pre_boil_sg} onChange={(v) => setData({ pre_boil_sg: v })} />
        </Field>
        <Field label={`Pre-boil volume (${u.label("gal")})`}>
          <UnitNum kind="gal" stepper step={0.25} decimals={2} placeholder="–" value={d.pre_boil_gal} onChange={(v) => setData({ pre_boil_gal: v })} />
        </Field>
        <Field label="OG">
          <NumInput stepper step={0.001} decimals={3} placeholder="–" value={d.og} onChange={(v) => setData({ og: v })} />
        </Field>
        <Field label={`Post-boil volume (${u.label("gal")})`}>
          <UnitNum kind="gal" stepper step={0.25} decimals={2} placeholder="–" value={d.post_boil_gal} onChange={(v) => setData({ post_boil_gal: v })} />
        </Field>
        <Field label="FG">
          <NumInput stepper step={0.001} decimals={3} placeholder="–" value={d.fg} onChange={(v) => setData({ fg: v })} />
        </Field>
      </div>

      <Field label="Notes">
        <textarea
          className="input"
          rows={4}
          placeholder="Tasting notes, what to change next time…"
          value={d.notes}
          onChange={(e) => setData({ notes: e.target.value })}
        />
      </Field>

      <h3>Actual vs planned</h3>
      <div className="row five">
        {actual?.efficiency ? (
          <Metric
            label="Mash efficiency"
            value={`${fixed(actual.efficiency.value, 1)}%`}
            delta={`${signed(actual.efficiency.delta, 1)} vs plan`}
            help="From pre-boil SG and pre-boil volume (planned volume if not entered)"
          />
        ) : (
          <Metric label="Mash efficiency" value="–" help="Enter pre-boil SG" />
        )}
        {actual?.og ? <Metric label="OG" value={fixed(actual.og.value, 3)} delta={`${signed(actual.og.delta_points, 0)} pts vs plan`} /> : <div />}
        {actual?.fg ? (
          <Metric label="FG" value={fixed(actual.fg.value, 3)} delta={`${signed(actual.fg.delta_points, 0)} pts vs plan`} deltaTone="inverse" />
        ) : (
          <div />
        )}
        {actual?.abv ? <Metric label="ABV" value={`${fixed(actual.abv.value, 1)}%`} delta={`${signed(actual.abv.delta, 1)} vs plan`} /> : <div />}
        {actual?.attenuation ? (
          <Metric label="Apparent attenuation" value={`${fixed(actual.attenuation.value, 0)}%`} delta={`${signed(actual.attenuation.delta, 0)} vs yeast avg`} />
        ) : (
          <div />
        )}
      </div>

      <div className="buttons">
        <button className="primary" onClick={onSave}>
          Save log
        </button>
        {log.id != null && <button onClick={onDelete}>Delete log</button>}
      </div>
    </>
  );
}
