import { useMemo, useState } from "react";
import { api } from "../api.js";
import { g } from "../format.js";

const range = (r, digits) => (!r ? "varies" : digits == null ? `${g(r[0])}–${g(r[1])}` : `${r[0].toFixed(digits)}–${r[1].toFixed(digits)}`);

// Columns for each tab: [key, heading, right-aligned?, show-as-text]
const TABS = {
  Grains: {
    rows: (ref) => ref.grains,
    cols: [["item", "Fermentable"], ["producer", "Producer"], ["category", "Category"], ["type", "Type"], ["lovibond", "°L", true], ["ppg", "PPG", true], ["origin", "Origin"], ["description", "Description", false, true], ["notes", "Notes"], ["source", "Source"]],
  },
  Hops: {
    rows: (ref) => ref.hops,
    cols: [
      ["name", "Hop"], ["origin", "Origin"], ["purpose", "Purpose"], ["type", "Type"], ["use", "Recommended use"], ["alpha_acid", "Avg alpha acid %", true],
      ["alpha_range", "Alpha %"], ["beta_range", "Beta %"], ["cohumulone_range", "Cohumulone %"], ["oil_range", "Oils (ml/100g)"],
      ["aroma", "Aroma", false, true], ["storage", "Storage"], ["substitutions", "Substitutions"], ["description", "Description", false, true], ["source", "Source"],
    ],
  },
  Yeast: {
    rows: (ref) => ref.yeasts,
    cols: [
      ["name", "Yeast"], ["code", "Code"], ["lab", "Lab"], ["type", "Type"], ["form", "Form"],
      ["attenuation", "Avg atten. %", true], ["flocculation", "Flocc."], ["temp_range_f", "Temp (°F)"],
      ["best_for", "Best for"], ["notes", "Notes", false, true],
    ],
  },
  Styles: {
    rows: (ref) =>
      ref.styles.map((s) => ({ name: s.name, abv: range(s.abv), ibu: range(s.ibu), og: range(s.og, 3), fg: range(s.fg, 3), srm: range(s.srm) })),
    cols: [["name", "Style"], ["abv", "ABV"], ["ibu", "IBU"], ["og", "OG"], ["fg", "FG"], ["srm", "SRM"]],
  },
};

export default function Ingredients({ reference, setReference }) {
  const [tab, setTab] = useState("Grains");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState(null); // { key, dir }
  const [busy, setBusy] = useState(false);

  const { cols, rows } = useMemo(() => {
    const def = TABS[tab];
    let list = def.rows(reference);
    const q = query.trim().toLowerCase();
    if (q) list = list.filter((row) => def.cols.some(([key]) => String(row[key] ?? "").toLowerCase().includes(q)));
    if (sort && def.cols.some(([key]) => key === sort.key)) {
      list = [...list].sort((a, b) => {
        const x = a[sort.key] ?? "";
        const y = b[sort.key] ?? "";
        const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true });
        return sort.dir * c;
      });
    }
    // Hide columns the chosen reference file doesn't have (the two hop lists carry different details).
    const all = def.rows(reference);
    const cols = def.cols.filter(([key]) => all.some((row) => row[key] != null && row[key] !== ""));
    return { cols, rows: list };
  }, [reference, tab, query, sort]);

  async function reload() {
    setBusy(true);
    try {
      setReference(await api.post("/api/reference/reload"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Ingredients</h1>
      <input className="input" placeholder="Search, e.g. crystal, citra, WLP001, stout" value={query} onChange={(e) => setQuery(e.target.value)} />

      <div className="tabs" role="tablist">
        {Object.keys(TABS).map((name) => (
          <button key={name} role="tab" aria-selected={tab === name} className={tab === name ? "active" : ""} onClick={() => (setTab(name), setSort(null))}>
            {name}
          </button>
        ))}
      </div>

      <div className="table-wrap tall">
        <table className="grid plain sortable">
          <thead>
            <tr>
              {cols.map(([key, heading, right]) => (
                <th
                  key={key}
                  className={right ? "r" : ""}
                  onClick={() => setSort((s) => ({ key, dir: s?.key === key ? -s.dir : 1 }))}
                  title="Click to sort"
                >
                  {heading}
                  {sort?.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {cols.map(([key, , right, wrap]) => (
                  <td key={key} className={`${right ? "r" : ""} ${wrap ? "wrap" : ""}`}>
                    {typeof row[key] === "number" ? g(row[key]) : row[key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">{rows.length} shown</p>
      <button onClick={reload} disabled={busy}>
        Reload data files
      </button>

      <h2>Data sources</h2>
      <ul className="sources">
        <li><strong>Fermentables:</strong> maltster product data (Briess, Castle Malting, Crisp, Simpsons, Viking Malt, Weyermann and Rahr via BSG); sugar gravity calculated from composition; candi syrup colour from Candi Syrup Inc and MoreBeer listings; fruit sugar from 21 CFR 101.30 Brix values and Oregon Fruit puree spec sheets. Each row's source column gives the detail.</li>
        <li>
          <strong>Hops:</strong> <a href="https://www.usahops.org" target="_blank" rel="noreferrer">Hop Growers of America</a> (Variety Manual 2011, Variety Snapshot 2020),{" "}
          <a href="https://nzhops.co.nz/collections/new-zealand-hops" target="_blank" rel="noreferrer">NZ Hops</a>,{" "}
          <a href="https://www.britishhops.org.uk/varieties/" target="_blank" rel="noreferrer">British Hops</a>, and{" "}
          <a href="https://www.barthhaas.com" target="_blank" rel="noreferrer">BarthHaas</a> Hop Harvest Guides 2019–2022. The Source column gives the source for each hop.
        </li>
        <li><strong>Yeast:</strong> <a href="https://www.brewunited.com" target="_blank" rel="noreferrer">BrewUnited</a> yeast list.</li>
        <li><strong>Beer styles:</strong> <a href="https://www.bjcp.org/beer-styles/" target="_blank" rel="noreferrer">BJCP 2021 Beer Style Guidelines</a>.</li>
      </ul>
    </>
  );
}
