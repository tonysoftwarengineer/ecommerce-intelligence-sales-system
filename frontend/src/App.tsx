import { lazy, Suspense, useState } from "react";

import "./App.css";
import { SourceSelection } from "./components/SourceSelection";

type View = "sources" | "upload" | "sample";

const BusinessWorkspace = lazy(() =>
  import("./components/BusinessWorkspace").then((module) => ({
    default: module.BusinessWorkspace,
  })),
);

const FEEDBACK_URL =
  import.meta.env.VITE_FEEDBACK_URL ??
  "https://github.com/tonysoftwarengineer/ecommerce-intelligence-sales-system/issues/new?template=feedback.yml";

function App() {
  return (
    <>
      <AppView />
      <footer className="app-feedback">
        <a href={FEEDBACK_URL} target="_blank" rel="noopener noreferrer">
          Give feedback
        </a>
        <span> · opens a public GitHub form; please do not include private data.</span>
      </footer>
    </>
  );
}

function AppView() {
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
