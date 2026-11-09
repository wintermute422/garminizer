import { createElement } from "react";
import { useMode } from "@/lib/preferences";
import { sportColor, sportIcon, sportLabel } from "@/lib/sports";
import { wash } from "@/lib/tokens";

/** The sport's icon (decorative unless `labelled`), optionally in the sport colour. */
export function SportIcon({
  group,
  size = 16,
  colored = false,
  labelled = false,
}: {
  group: string;
  size?: number;
  colored?: boolean;
  labelled?: boolean;
}) {
  const mode = useMode();
  return createElement(sportIcon(group), {
    size,
    color: colored ? sportColor(group, mode) : undefined,
    "aria-hidden": !labelled,
    "aria-label": labelled ? sportLabel(group) : undefined,
  });
}

/** Square badge with the sport icon on a soft wash of the sport colour. */
export function SportBadge({ group, size = 32 }: { group: string; size?: number }) {
  const mode = useMode();
  const color = sportColor(group, mode);
  return (
    <span
      className="inline-flex shrink-0 items-center justify-center rounded-control"
      style={{ background: wash(color, 0.13), color, width: size, height: size }}
      title={sportLabel(group)}
    >
      <SportIcon group={group} size={Math.round(size / 2)} />
      <span className="sr-only">{sportLabel(group)}</span>
    </span>
  );
}
