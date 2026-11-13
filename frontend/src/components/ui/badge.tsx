import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "outline" | "success" | "warning" | "destructive" | "owner" | "admin" | "operator" | "viewer";
}

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  const variants = {
    default: "bg-slate-900 text-white",
    secondary: "bg-slate-100 text-slate-900",
    outline: "text-slate-800 border border-slate-300",
    success: "bg-emerald-50 text-emerald-700 border border-emerald-200",
    warning: "bg-amber-50 text-amber-700 border border-amber-200",
    destructive: "bg-rose-50 text-rose-700 border border-rose-200",
    owner: "bg-purple-50 text-purple-700 border border-purple-200 font-semibold",
    admin: "bg-blue-50 text-blue-700 border border-blue-200 font-semibold",
    operator: "bg-teal-50 text-teal-700 border border-teal-200 font-semibold",
    viewer: "bg-slate-100 text-slate-700 border border-slate-200 font-medium",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}
