import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";
import { Icon, type IconName } from "./Icon";

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "default" | "small";
  icon?: IconName;
}

export function Button({
  variant = "secondary",
  size = "default",
  icon,
  className,
  children,
  ...rest
}: ButtonProps) {
  const classes = [
    styles.button,
    styles[variant],
    size === "small" ? styles.small : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={classes} {...rest}>
      {icon ? <Icon name={icon} size={size === "small" ? 14 : 16} /> : null}
      {children}
    </button>
  );
}
