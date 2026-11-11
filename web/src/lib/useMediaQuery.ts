import { useSyncExternalStore } from "react";

/** Phone-width viewport: dense bars and heatmap cells drop their 1px surface gaps. */
export const NARROW = "(max-width: 640px)";

/** True while the media query matches (re-renders on change; false during SSR/tests). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia?.(query);
      mq?.addEventListener("change", onChange);
      return () => mq?.removeEventListener("change", onChange);
    },
    () => window.matchMedia?.(query).matches ?? false,
    () => false,
  );
}
