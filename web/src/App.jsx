import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { Banner, Combobox, Expander } from "./components.jsx";
import { todayISO } from "./format.js";
import BrewDay from "./pages/BrewDay.jsx";
import Calculator from "./pages/Calculator.jsx";
import Ingredients from "./pages/Ingredients.jsx";
import { UnitToggle } from "./units.jsx";

const PAGES = [
  { id: "calculator", title: "Calculator", icon: "🧮" },
  { id: "brew-day", title: "Brew Day", icon: "📋" },
  { id: "ingredients", title: "Ingredients", icon: "🌾" },
];
const EMPTY_LOG = { pre_boil_sg: null, pre_boil_gal: null, og: null, post_boil_gal: null, fg: null, mash_readings: [], notes: "" };
const DRAFT_KEY = "brewcalc.draft";

function usePage() {
  const read = () => (PAGES.find((p) => `#/${p.id}` === window.location.hash) ?? PAGES[0]).id;
  const [page, setPage] = useState(read);
  useEffect(() => {
    const on = () => setPage(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return page;
}

const loadDraft = () => {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY));
  } catch {
    return null;
  }
};

export default function App() {
  const page = usePage();
  const [boot, setBoot] = useState({ status: "loading" });
  const [reference, setReference] = useState(null);
  const [defaults, setDefaults] = useState(null);
  const [recipes, setRecipes] = useState([]);
  const [logs, setLogs] = useState([]);

  // The recipe being edited. `version` changes whenever a different recipe is loaded, so the page's own
  // fields (like the typed step temperatures) start fresh.
  const [recipe, setRecipe] = useState(null);
  const [recipeId, setRecipeId] = useState(null);
  const [savedJson, setSavedJson] = useState(null);
  const [version, setVersion] = useState(0);
  const [log, setLog] = useState(null);
  const [toast, setToast] = useState(null);
  const [menuOpen, setMenuOpen] = useState(false); // only matters on narrow screens
  // Wide screens: the sidebar can be tucked away, and that choice is remembered.
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("brewcalc.sidebarCollapsed") === "1";
    } catch {
      return false;
    }
  });
  const toggleSidebar = (value) => {
    setCollapsed(value);
    try {
      localStorage.setItem("brewcalc.sidebarCollapsed", value ? "1" : "0");
    } catch {
      /* storage unavailable: carry on without it */
    }
  };
  const toastTimer = useRef(null);

  const say = useCallback((text, kind = "ok") => {
    setToast({ text, kind });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 3000);
  }, []);

  const loadRecipe = useCallback((r, id) => {
    setRecipe(r);
    setRecipeId(id);
    setSavedJson(id != null ? JSON.stringify(r) : null);
    setVersion((v) => v + 1);
  }, []);

  const refreshRecipes = useCallback(() => api.get("/api/recipes").then(setRecipes), []);
  const refreshLogs = useCallback(() => api.get("/api/logs").then(setLogs), []);

  // First load: reference data, defaults, saved recipes and logs, then whatever you were editing last.
  useEffect(() => {
    (async () => {
      try {
        const [ref, def, rs, ls] = await Promise.all([api.get("/api/reference"), api.get("/api/defaults"), api.get("/api/recipes"), api.get("/api/logs")]);
        setReference(ref);
        setDefaults(def);
        setRecipes(rs);
        setLogs(ls);
        const draft = loadDraft();
        if (draft?.recipe) {
          const r = await api.post("/api/normalize", draft.recipe);
          setRecipe(r);
          setRecipeId(draft.recipeId ?? null);
          setSavedJson(draft.savedJson ?? null);
        } else {
          setRecipe(def.example);
        }
        setBoot({ status: "ready" });
      } catch (e) {
        setBoot({ status: "failed", message: e.message });
      }
    })();
  }, []);

  // Keep the recipe in this browser so a refresh doesn't lose unsaved work.
  useEffect(() => {
    if (!recipe) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ recipe, recipeId, savedJson }));
    } catch {
      /* storage unavailable: carry on without it */
    }
  }, [recipe, recipeId, savedJson]);

  if (boot.status === "loading") return <div className="splash">Loading…</div>;
  if (boot.status === "failed") {
    return (
      <div className="splash">
        <Banner kind="error">
          Couldn't reach the calculator's server ({boot.message}). Start it with <code>run_react.command</code> and reload this page.
        </Banner>
      </div>
    );
  }

  const unsaved = JSON.stringify(recipe) !== savedJson;

  async function openRecipe(id) {
    loadRecipe(await api.get(`/api/recipes/${id}`), id);
  }
  async function save(asNew) {
    try {
      let id = recipeId;
      if (id == null || asNew) id = (await api.post("/api/recipes", recipe)).id;
      else await api.put(`/api/recipes/${id}`, recipe);
      setRecipeId(id);
      setSavedJson(JSON.stringify(recipe));
      await refreshRecipes();
      say(asNew ? "Saved a copy" : `Saved “${recipe.name}”`);
    } catch (e) {
      say(`Couldn't save: ${e.message}`, "error");
    }
  }
  async function remove() {
    await api.del(`/api/recipes/${recipeId}`);
    await refreshRecipes();
    loadRecipe(defaults.default, null);
  }
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(recipe, null, 2)], { type: "application/json" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `${recipe.name || "recipe"}.json` });
    a.click();
    URL.revokeObjectURL(url);
  }
  async function importFile(file) {
    try {
      loadRecipe(await api.post("/api/normalize", JSON.parse(await file.text())), null);
    } catch (e) {
      say(`Couldn't read that file: ${e.message}`, "error");
    }
  }

  async function openLog(id) {
    const l = await api.get(`/api/logs/${id}`);
    setLog({ id: l.id, brew_date: l.brew_date, data: { ...EMPTY_LOG, ...l.data }, recipe_id: l.recipe_id, snapshot: l.recipe_snapshot });
  }
  function newLog() {
    setLog({ id: null, brew_date: todayISO(), data: { ...EMPTY_LOG }, recipe_id: recipeId, snapshot: JSON.parse(JSON.stringify(recipe)) });
  }
  async function saveLog() {
    try {
      const body = { brew_date: log.brew_date, data: log.data, recipe_id: log.recipe_id, recipe_snapshot: log.snapshot };
      let id = log.id;
      if (id == null) id = (await api.post("/api/logs", body)).id;
      else await api.put(`/api/logs/${id}`, body);
      setLog((l) => ({ ...l, id }));
      await refreshLogs();
      say("Brew log saved");
    } catch (e) {
      say(`Couldn't save: ${e.message}`, "error");
    }
  }
  async function deleteLog() {
    await api.del(`/api/logs/${log.id}`);
    setLog(null);
    await refreshLogs();
  }

  return (
    <div className={`shell ${collapsed ? "collapsed" : ""}`}>
      {collapsed && (
        <button className="expand-btn" title="Show the sidebar" aria-label="Show the sidebar" onClick={() => toggleSidebar(false)}>
          »
        </button>
      )}
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <button className="menu-toggle" onClick={() => setMenuOpen((o) => !o)}>
          ☰ Menu
        </button>
        <button className="collapse-btn" title="Hide the sidebar" aria-label="Hide the sidebar" onClick={() => toggleSidebar(true)}>
          «
        </button>
        <div className="side-body">
        <nav className="nav">
          {PAGES.map((p) => (
            <a key={p.id} href={`#/${p.id}`} className={p.id === page ? "active" : ""}>
              <span aria-hidden="true">{p.icon}</span> {p.title}
            </a>
          ))}
        </nav>
        <hr />
        <UnitToggle />
        <hr />
        {page === "calculator" && (
          <RecipePanel
            {...{ recipes, recipeId, unsaved, recipe }}
            onOpen={openRecipe}
            onNew={() => loadRecipe(defaults.default, null)}
            onSave={() => save(false)}
            onSaveNew={() => save(true)}
            onDownload={download}
            onImport={importFile}
            onExample={() => loadRecipe(defaults.example, null)}
            onDelete={remove}
          />
        )}
        {page === "brew-day" && <LogPanel {...{ logs, recipe }} onOpen={openLog} onNew={newLog} />}
        </div>
      </aside>

      <main className="main">
        <div className="main-inner" key={`${page}-${version}`}>
          {page === "calculator" && <Calculator recipe={recipe} setRecipe={setRecipe} reference={reference} onSave={() => save(false)} unsaved={unsaved} isNew={recipeId == null} />}
          {page === "brew-day" && <BrewDay log={log} setLog={setLog} onSave={saveLog} onDelete={deleteLog} />}
          {page === "ingredients" && <Ingredients reference={reference} setReference={setReference} />}
        </div>
      </main>

      {toast && <div className={`toast ${toast.kind}`}>{toast.text}</div>}
    </div>
  );
}

function RecipePanel({ recipes, recipeId, unsaved, recipe, onOpen, onNew, onSave, onSaveNew, onDownload, onImport, onExample, onDelete }) {
  const [choice, setChoice] = useState("");
  const options = recipes.map((r) => ({ value: String(r.id), label: r.name + (r.style ? ` · ${r.style}` : "") }));
  return (
    <>
      <h3>Recipe</h3>
      <label className="field">
        <span className="field-label">Saved recipes</span>
        <Combobox options={options} value={choice} onChange={setChoice} placeholder="Open…" />
      </label>
      <div className="buttons two">
        <button disabled={!choice} onClick={() => onOpen(Number(choice))}>
          Open
        </button>
        <button onClick={onNew}>New</button>
      </div>
      <hr />
      {unsaved && <p className="caption">{recipeId != null ? "Unsaved changes" : "Not saved yet"}</p>}
      <div className="buttons two">
        <button className="primary" onClick={onSave}>
          Save
        </button>
        <button disabled={recipeId == null} onClick={onSaveNew}>
          Save as new
        </button>
      </div>
      <Expander title="Import / export">
        <div className="stack">
          <button onClick={onDownload}>Download recipe (.json)</button>
          <label className="file">
            <span className="field-label">Open a recipe file</span>
            <input
              type="file"
              accept=".json,application/json"
              onChange={(e) => {
                if (e.target.files[0]) onImport(e.target.files[0]);
                e.target.value = "";
              }}
            />
          </label>
          <button onClick={onExample}>Load spreadsheet example</button>
        </div>
      </Expander>
      {recipeId != null && (
        <Expander title="Delete">
          <button className="danger" onClick={onDelete}>
            Delete this recipe
          </button>
        </Expander>
      )}
    </>
  );
}

function LogPanel({ logs, recipe, onOpen, onNew }) {
  const [choice, setChoice] = useState("");
  const options = logs.map((l) => ({ value: String(l.id), label: `${l.brew_date} · ${l.recipe_name || "no recipe"}` }));
  return (
    <>
      <h3>Brew logs</h3>
      <label className="field">
        <span className="field-label">Past brews</span>
        <Combobox options={options} value={choice} onChange={setChoice} placeholder="Open…" />
      </label>
      <div className="buttons">
        <button disabled={!choice} onClick={() => onOpen(Number(choice))}>
          Open log
        </button>
        <button className="primary" onClick={onNew}>
          New log for “{recipe.name}”
        </button>
      </div>
      <p className="caption">New logs use the recipe open on the Calculator page, as it is right now.</p>
    </>
  );
}
