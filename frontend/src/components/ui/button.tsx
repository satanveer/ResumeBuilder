import * as React from "react";

import { cn } from "@/lib/utils";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "default" | "secondary";
};

export function Button({ className, variant = "default", ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "default" && "bg-slate-900 text-white hover:bg-slate-700",
        variant === "secondary" && "bg-slate-200 text-slate-900 hover:bg-slate-300",
        className
      )}
      {...props}
    />
  );
}
