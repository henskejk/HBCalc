import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { UnitsProvider } from "./units.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <UnitsProvider>
    <App />
  </UnitsProvider>,
);
