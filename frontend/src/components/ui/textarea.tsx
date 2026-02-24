import * as React from "react";

import { cn } from "@/lib/utils";

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-[140px] w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none ring-offset-white placeholder:text-slate-400 focus-visible:ring-2 focus-visible:ring-slate-900",
        className
      )}
      {...props}
    />
  );
}
