import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { fixed, g } from "./format.js";

// Recipes and brew logs are always stored (and calculated) in imperial units. The imperial/metric switch only changes
// what is shown and typed: values are converted on the way out to the screen and back on the way in. Switching is
// therefore lossless, and filled-in tables simply re-display in the other system.

const GAL = 3.785411784; // litres
const QT = 0.946352946; // litres
const LB = 0.45359237; // kilograms
const OZ = 28.349523125; // grams

/** Each quantity: label per system, conversions, and the step / decimals used for metric input boxes. */
export const KINDS = {
  gal: { imp: "gal", met: "L", to: (x) => x * GAL, from: (x) => x / GAL, step: 0.5, dec: 2 },
  qt: { imp: "qt", met: "L", to: (x) => x * QT, from: (x) => x / QT, step: 0.5, dec: 2 },
  lb: { imp: "lb", met: "kg", to: (x) => x * LB, from: (x) => x / LB, step: 0.1, dec: 2 },
  oz: { imp: "oz", met: "g", to: (x) => x * OZ, from: (x) => x / OZ, step: 1, dec: 1 },
  temp: { imp: "°F", met: "°C", to: (f) => ((f - 32) * 5) / 9, from: (c) => (c * 9) / 5 + 32, step: 1, dec: 1 },
  dtemp: { imp: "°F", met: "°C", to: (x) => (x * 5) / 9, from: (x) => (x * 9) / 5, step: 0.5, dec: 1 }, // a temperature difference
  qtlb: { imp: "qt/lb", met: "L/kg", to: (x) => (x * QT) / LB, from: (x) => (x * LB) / QT, step: 0.1, dec: 2 },
  gallb: { imp: "gal/lb", met: "L/kg", to: (x) => (x * GAL) / LB, from: (x) => (x * LB) / GAL, step: 0.05, dec: 2 },
  ppg: { imp: "points/gal", met: "points/L", to: (x) => x / GAL, from: (x) => x * GAL, step: 1, dec: 1 },
};

const KEY = "brewcalc.units";
const Ctx = createContext(null);

export function UnitsProvider({ children }) {
  const [system, setSystemState] = useState(() => {
    try {
      return localStorage.getItem(KEY) === "metric" ? "metric" : "imperial";
    } catch {
      return "imperial";
    }
  });
  const setSystem = useCallback((s) => {
    setSystemState(s);
    try {
      localStorage.setItem(KEY, s);
    } catch {
      /* storage unavailable: carry on without it */
    }
  }, []);
  const value = useMemo(() => {
    const metric = system === "metric";
    return {
      system,
      metric,
      setSystem,
      /** The unit's name in the current system, e.g. "gal" or "L". */
      label: (kind) => (metric ? KINDS[kind].met : KINDS[kind].imp),
      /** An imperial value converted for display (unrounded). */
      toShown: (kind, x) => (metric ? KINDS[kind].to(x) : x),
      /** A displayed value converted back to imperial. */
      toImperial: (kind, x) => (metric ? KINDS[kind].from(x) : x),
      /** "5.5 gal" / "20.82 L". Imperial drops trailing zeros unless `digits` is given; metric uses `digits` or the kind's default. */
      show: (kind, x, digits) => {
        if (x == null || Number.isNaN(x)) return "–";
        const k = KINDS[kind];
        if (metric) return `${digits == null ? g(Number(k.to(x).toFixed(k.dec))) : fixed(k.to(x), digits)} ${k.met}`;
        return `${digits == null ? g(x) : fixed(x, digits)} ${k.imp}`;
      },
      /** A "65-70" range given in °F, shown in the current system. */
      tempRange: (text) => {
        if (!text) return "–";
        if (!metric) return `${text} °F`;
        return `${text.replace(/[\d.]+/g, (n) => String(Math.round(KINDS.temp.to(Number(n)))))} °C`;
      },
    };
  }, [system, setSystem]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useUnits = () => useContext(Ctx);

/** The Imperial / Metric switch. */
export function UnitToggle() {
  const { system, setSystem } = useUnits();
  return (
    <div className="unit-toggle">
      <span className="field-label">Units</span>
      <div className="seg" role="group" aria-label="Units">
        {[
          ["imperial", "Imperial"],
          ["metric", "Metric"],
        ].map(([key, label]) => (
          <button key={key} type="button" className={system === key ? "on" : ""} aria-pressed={system === key} onClick={() => setSystem(key)}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
