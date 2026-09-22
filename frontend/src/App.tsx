import { lazy, Suspense, useState } from "react";

import "./App.css";
import { SourceSelection } from "./components/SourceSelection";

type View = "sources" | "olist" | "upload";

const OlistDashboard = lazy(() =>
  import("./components/OlistDashboard").then((module) => ({ default: module.OlistDashboard })),
);
const BusinessWorkspace = lazy(() =>
  import("./components/BusinessWorkspace").then((module) => ({
    default: module.BusinessWorkspace,
  })),
);

function App() {
  const [view, setView] = useState<View>(() =>
    sessionStorage.getItem("sales-analysis-id") ? "upload" : "sources",
  );

  if (view === "olist") {
    return (
      <Suspense fallback={<LoadingFeature />}>
        <OlistDashboard onBack={() => setView("sources")} />
      </Suspense>
    );
  }
  if (view === "upload") {
    return (
      <Suspense fallback={<LoadingFeature />}>
        <BusinessWorkspace onBack={() => setView("sources")} />
      </Suspense>
    );
  }

  return (
    <SourceSelection
      onSelectOlist={() => setView("olist")}
      onSelectUpload={() => setView("upload")}
    />
  );
}

function LoadingFeature() {
  return (
    <div className="status">
      <div className="spinner" aria-hidden="true" />
      <p>Opening workspace…</p>
    </div>
  );
}

export default App;
