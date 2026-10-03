import { lazy, Suspense, useState } from "react";

import "./App.css";
import { SourceSelection } from "./components/SourceSelection";

type View = "sources" | "upload" | "sample";

const BusinessWorkspace = lazy(() =>
  import("./components/BusinessWorkspace").then((module) => ({
    default: module.BusinessWorkspace,
  })),
);

function App() {
  const [view, setView] = useState<View>(() =>
    sessionStorage.getItem("sales-analysis-id") ? "upload" : "sources",
  );

  if (view === "upload" || view === "sample") {
    return (
      <Suspense fallback={<LoadingFeature />}>
        <BusinessWorkspace onBack={() => setView("sources")} sampleMode={view === "sample"} />
      </Suspense>
    );
  }

  return (
    <SourceSelection
      onSelectUpload={() => {
        sessionStorage.removeItem("sales-analysis-id");
        sessionStorage.removeItem("sales-analysis-source");
        setView("upload");
      }}
      onSelectSample={() => {
        sessionStorage.removeItem("sales-analysis-id");
        setView("sample");
      }}
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
