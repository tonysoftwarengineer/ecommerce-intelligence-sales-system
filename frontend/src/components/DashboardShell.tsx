import { useEffect, useRef, useState, type ReactNode } from "react";

export function DashboardStatus({ message }: { message: string }) {
  return (
    <div className="status">
      <div className="spinner" aria-hidden="true" />
      <p>{message}</p>
    </div>
  );
}

export interface DashboardSection {
  id: string;
  label: string;
  tag?: string;
}

export interface DashboardSectionGroup {
  label: string;
  sections: DashboardSection[];
}

interface DashboardLayoutProps {
  eyebrow?: string;
  title: string;
  subtitle: string;
  datasetLabel: string;
  groups: DashboardSectionGroup[];
  onBack: () => void;
  headerActions?: ReactNode;
  navActions?: ReactNode;
  children: ReactNode;
}

// One page with jump links rather than tabs: every section stays rendered, so
// in-progress work (a product-demand evaluation, a document answer) is never
// unmounted by navigating, and browser find/print still see the whole report.
export function DashboardLayout({
  eyebrow,
  title,
  subtitle,
  datasetLabel,
  groups,
  onBack,
  headerActions,
  navActions,
  children,
}: DashboardLayoutProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sections = groups.flatMap((group) => group.sections);
  const activeId = useActiveSection(sections.map((section) => section.id));
  const activeLabel = sections.find((section) => section.id === activeId)?.label;

  // The setup steps are long, and the browser keeps their scroll position when
  // the dashboard replaces them; start the report at its top instead.
  useEffect(() => {
    if (!document.getElementById(window.location.hash.slice(1))) window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      menuButton.current?.focus();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  return (
    <div className="dash">
      <nav className="dash-nav" aria-label="Dashboard sections">
        <div className="dash-nav__bar">
          <div className="dash-nav__brand">
            <button
              type="button"
              className="icon-button"
              onClick={onBack}
              aria-label="Back to data sources"
            >
              ←
            </button>
            <span className="header__mark" aria-hidden="true" />
            <span className="dash-nav__name">Sales Intelligence</span>
          </div>
          <button
            ref={menuButton}
            type="button"
            className="dash-nav__toggle"
            aria-expanded={menuOpen}
            aria-controls="dashboard-section-links"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span aria-hidden="true">{menuOpen ? "✕" : "☰"}</span>
            {menuOpen ? "Close" : "Sections"}
          </button>
        </div>
        {activeLabel ? (
          <p className="dash-nav__current">
            You are in: <strong>{activeLabel}</strong>
          </p>
        ) : null}
        <div
          id="dashboard-section-links"
          className={`dash-nav__panel${menuOpen ? " dash-nav__panel--open" : ""}`}
        >
          <p className="dash-nav__dataset">{datasetLabel}</p>
          {groups.map((group) => (
            <div className="dash-nav__group" key={group.label}>
              <p className="dash-nav__group-label">{group.label}</p>
              {group.sections.map((section) => (
                <a
                  key={section.id}
                  href={`#${section.id}`}
                  className="dash-nav__link"
                  aria-current={section.id === activeId ? "true" : undefined}
                  onClick={() => setMenuOpen(false)}
                >
                  <span>{section.label}</span>
                  {section.tag ? <span className="dash-nav__tag">{section.tag}</span> : null}
                </a>
              ))}
            </div>
          ))}
          {navActions ? <div className="dash-nav__actions">{navActions}</div> : null}
        </div>
      </nav>

      <main className="dash-main">
        <header className="dash-header">
          <div>
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            <h1 className="dash-header__title">{title}</h1>
            <p className="dash-header__subtitle">{subtitle}</p>
          </div>
          {headerActions ? <div className="dash-header__actions">{headerActions}</div> : null}
        </header>
        {children}
      </main>
    </div>
  );
}

// Highlights the section nearest the top of the viewport. Without
// IntersectionObserver (old browsers, some test runners) the first section stays
// marked, which is still a correct starting point.
function useActiveSection(ids: string[]): string | undefined {
  const [activeId, setActiveId] = useState<string | undefined>(ids[0]);
  const key = ids.join("|");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const targets = key
      .split("|")
      .map((id) => document.getElementById(id))
      .filter((element): element is HTMLElement => element !== null);
    if (targets.length === 0) return;
    const visible = new Set<string>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) visible.add(entry.target.id);
          else visible.delete(entry.target.id);
        }
        const first = targets.find((target) => visible.has(target.id));
        if (first) setActiveId(first.id);
      },
      { rootMargin: "-15% 0px -60% 0px" },
    );
    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, [key]);

  return activeId;
}
