import type { ReactNode } from "react";

export function DashboardStatus({ message }: { message: string }) {
  return (
    <div className="status">
      <div className="spinner" aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}

interface DashboardHeaderProps {
  title: string;
  period: string;
  context: string;
  onBack: () => void;
  actions?: ReactNode;
}

export function DashboardHeader({
  title,
  period,
  context,
  onBack,
  actions,
}: DashboardHeaderProps) {
  return (
    <header className="header">
      <div className="header__brand">
        <button type="button" className="icon-button" onClick={onBack} aria-label="Back">
          ←
        </button>
        <span className="header__mark" aria-hidden="true" />
        <h1 className="header__title">{title}</h1>
      </div>
      <div className="header__meta">
        {period ? <span className="chip">{period}</span> : null}
        <span className="chip chip--accent">{context}</span>
        {actions}
      </div>
    </header>
  );
}
