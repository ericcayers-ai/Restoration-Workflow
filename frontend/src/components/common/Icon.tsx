/*
 * A single custom line-icon set, 1.5px stroke, unfilled, 24px grid
 * (UI_DESIGN.md section 4) — hand-drawn rather than a vendored library, both
 * to keep the bundle small and so the corner treatment can be deliberately
 * a little less mechanically uniform than a templated set, per that section.
 * Never used as the sole carrier of meaning-bearing information (section 6);
 * every place an icon signals status also carries a text label.
 */

import type { SVGProps } from "react";

export type IconName =
  | "aperture"
  | "contact-sheet"
  | "loupe"
  | "tray"
  | "splice"
  | "dial"
  | "upload"
  | "image"
  | "compare"
  | "flow"
  | "save"
  | "export"
  | "close"
  | "chevron-down"
  | "chevron-right"
  | "contrast"
  | "command"
  | "play"
  | "trash"
  | "plus"
  | "warning"
  | "check"
  | "spinner";

const PATHS: Record<IconName, string> = {
  aperture:
    "M12 3v4.2M12 16.8V21M3 12h4.2M16.8 12H21M5.8 5.8l3 3M15.2 15.2l3 3M18.2 5.8l-3 3M8.8 15.2l-3 3M12 8.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2Z",
  "contact-sheet":
    "M3.5 3.5h6v6h-6zM14.5 3.5h6v6h-6zM3.5 14.5h6v6h-6zM14.5 14.5h6v6h-6z",
  loupe: "M11 4.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM15.8 15.8 20.5 20.5",
  tray:
    "M3.5 13h4.2l1.6 2.4h5.4l1.6-2.4h4.2M3.5 13v5.5a1 1 0 0 0 1 1h15a1 1 0 0 0 1-1V13M12 3.5v8M12 11.5l-3-3M12 11.5l3-3",
  splice:
    "M5 6.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM19 13.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4ZM7 8.5c3 0 3 5 5 5h5",
  dial: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16ZM12 8v4l3 2",
  upload: "M12 4v11M12 4l-4 4M12 4l4 4M5 16.5v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2",
  image:
    "M4.5 5.5h15a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1v-11a1 1 0 0 1 1-1ZM8 10.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM3.5 16.5l5-5 3 3 4-5 5 6",
  compare:
    "M9 4.5H6a1.5 1.5 0 0 0-1.5 1.5v12A1.5 1.5 0 0 0 6 19.5h3M15 4.5h3a1.5 1.5 0 0 1 1.5 1.5v12a1.5 1.5 0 0 1-1.5 1.5h-3M12 3v18",
  flow: "M4.5 6.5h5v4h-5zM14.5 6.5h5v4h-5zM9.5 8.5h5M9.5 17.5h5M14.5 13.5h5v4h-5zM12 10.5v3M12 13.5H9.5v4",
  save: "M5 4.5h11l3.5 3.5v11.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-14a1 1 0 0 1 1-1ZM8 4.5v5h7v-5M8 19v-6h8v6",
  export: "M12 15.5V4.5M12 4.5 8 8.5M12 4.5l4 4M5 15.5v3.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5",
  close: "M5.5 5.5l13 13M18.5 5.5l-13 13",
  "chevron-down": "M5.5 8.5 12 15l6.5-6.5",
  "chevron-right": "M8.5 5.5 15 12l-6.5 6.5",
  contrast: "M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17ZM12 3.5v17a8.5 8.5 0 0 0 0-17Z",
  command:
    "M8 6.5A2 2 0 1 0 6 8.5h2v-2ZM8 6.5v11M18 6.5A2 2 0 1 1 20 8.5h-2v-2ZM8 17.5A2 2 0 1 0 6 15.5h2v2ZM16 17.5v-11M16 17.5a2 2 0 1 0 2 2v-2h-2Z",
  play: "M6.5 4.5v15l13-7.5z",
  trash: "M5 7.5h14M9.5 7.5v-2a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v2M7.5 7.5l1 12a1 1 0 0 0 1 1h5a1 1 0 0 0 1-1l1-12",
  plus: "M12 5.5v13M5.5 12h13",
  warning: "M12 3.5 21 19.5H3ZM12 9.5v4.5M12 16.8v.1",
  check: "M4.5 12.5l5 5 10-11",
  spinner: "M12 3.5v3M12 17.5v3M17.5 6.5l-2 2M8.5 15.5l-2 2M20.5 12h-3M6.5 12h-3M17.5 17.5l-2-2M8.5 8.5l-2-2",
};

export function Icon({
  name,
  size = 20,
  className,
  ...rest
}: { name: IconName; size?: number } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
