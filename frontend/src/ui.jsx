import React from "react";

// shadcn/ui component patterns, themed with the workspace CSS tokens.
import { Slot, Dialog as DialogPrimitive } from "radix-ui";
import { cva } from "class-variance-authority";
import { X } from "lucide-react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}

const buttonVariants = cva("button", {
  variants: { variant: { default: "button-primary", ghost: "button-ghost", outline: "button-outline" } },
  defaultVariants: { variant: "default" },
});

export function Button({ className, variant, asChild, type = "button", ...props }) {
  const Component = asChild ? Slot.Root : "button";
  return <Component className={cn(buttonVariants({ variant }), className)} {...(!asChild && { type })} {...props} />;
}

export function Input({ className, ...props }) {
  return <input className={cn("input", className)} {...props} />;
}

export function Badge({ className, ...props }) {
  return <span className={cn("badge", className)} {...props} />;
}

export function Dialog({ trigger, title, description, children, open, onOpenChange, onOpenAutoFocus }) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
    <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="dialog-overlay" />
      <DialogPrimitive.Content className="dialog" onOpenAutoFocus={onOpenAutoFocus} {...(!description && { "aria-describedby": undefined })}>
        <header><DialogPrimitive.Title>{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close asChild><Button variant="ghost" aria-label="Close"><X size={16} /></Button></DialogPrimitive.Close>
        </header>
        {description && <DialogPrimitive.Description>{description}</DialogPrimitive.Description>}
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>;
}
