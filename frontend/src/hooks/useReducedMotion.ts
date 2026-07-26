import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

/** Recharts doesn't honour prefers-reduced-motion on its own — feed this into
 *  isAnimationActive so chart entrance motion follows the same rule the CSS does. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia(QUERY).matches);

  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const onChange = () => setReduced(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
