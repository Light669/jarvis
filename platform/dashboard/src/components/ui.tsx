import { AnimatePresence, motion } from "framer-motion";
import { Loader2, X } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { LEVEL_LABEL, type Level } from "../lib/api";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent-strong hover:bg-indigo-500 text-white shadow-sm",
  secondary: "bg-bg-raised hover:bg-line-strong text-ink border border-line-strong",
  ghost: "text-ink-muted hover:text-ink hover:bg-bg-muted",
  danger: "bg-red-600 hover:bg-red-500 text-white shadow-sm",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 font-medium rounded-md transition-colors duration-150",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50 disabled:cursor-not-allowed",
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm",
        VARIANTS[variant],
        className,
      )}
    >
      {loading && <Loader2 size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cx("bg-bg-subtle border border-line rounded-xl", className)}>{children}</div>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-xs font-medium text-ink-muted">{label}</span>
      {children}
      {hint && <span className="block text-xs text-ink-subtle">{hint}</span>}
    </label>
  );
}

const inputCls =
  "w-full px-3 py-2 text-sm bg-bg border border-line-strong rounded-md placeholder:text-ink-subtle " +
  "focus:outline-none focus:ring-2 focus:ring-accent/60 focus:border-transparent transition-shadow duration-150";

export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={cx(inputCls, p.className)} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea {...p} className={cx(inputCls, "font-mono text-xs leading-relaxed min-h-[96px]", p.className)} />
);
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={cx(inputCls, p.className)} />;

const LEVEL_STYLE: Record<Level, string> = {
  chef: "bg-amber-400/10 text-amber-300 border-amber-400/30",
  responsable: "bg-indigo-400/10 text-indigo-300 border-indigo-400/30",
  salarie: "bg-sky-400/10 text-sky-300 border-sky-400/30",
  apprenti: "bg-emerald-400/10 text-emerald-300 border-emerald-400/30",
};

const SHORT: Record<Level, string> = { chef: "Chef", responsable: "Resp.", salarie: "Salarié", apprenti: "Apprenti" };

export function LevelBadge({ level, short }: { level: Level; short?: boolean }) {
  return (
    <motion.span
      key={level}
      initial={{ scale: 0.6, rotate: -12, opacity: 0 }}
      animate={{ scale: 1, rotate: 0, opacity: 1 }}
      transition={{ type: "spring", stiffness: 400, damping: 18 }}
      className={cx("inline-flex items-center px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-full border whitespace-nowrap shrink-0", LEVEL_STYLE[level])}
    >
      {short ? SHORT[level] : LEVEL_LABEL[level]}
    </motion.span>
  );
}

const TONES = {
  gray: "bg-zinc-400/10 text-zinc-300 border-zinc-400/20",
  green: "bg-emerald-400/10 text-emerald-300 border-emerald-400/20",
  orange: "bg-amber-400/10 text-amber-300 border-amber-400/25",
  red: "bg-red-400/10 text-red-300 border-red-400/25",
  blue: "bg-sky-400/10 text-sky-300 border-sky-400/25",
  violet: "bg-indigo-400/10 text-indigo-300 border-indigo-400/25",
};
export type Tone = keyof typeof TONES;

export function Badge({ tone = "gray", children, dot }: { tone?: Tone; children: ReactNode; dot?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full border whitespace-nowrap", TONES[tone])}>
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export const STATUT_TONE: Record<string, Tone> = {
  // demandes / tâches / skills
  en_attente: "orange", escaladee: "red", acceptee: "green", refusee: "gray",
  en_cours: "blue", terminee: "green", erreur: "red", gelee: "blue", bloquee: "orange",
  brouillon: "gray", teste: "blue", approuve: "green", obsolete: "gray",
  actif: "green", pause: "blue", archive: "gray",
  info: "gray", attention: "orange", grave: "red", critique: "red",
};

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-12 px-6 gap-2">
      {icon && <div className="text-ink-subtle mb-1">{icon}</div>}
      <div className="text-sm font-medium text-ink">{title}</div>
      {children && <div className="text-xs text-ink-muted max-w-sm">{children}</div>}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex justify-center py-10 text-ink-subtle">
      <Loader2 className="animate-spin" size={18} />
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-start justify-center p-6 overflow-y-auto" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
          <motion.div
            role="dialog"
            aria-label={title}
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className={cx("relative w-full mt-10 bg-bg-subtle border border-line-strong rounded-xl shadow-2xl", wide ? "max-w-3xl" : "max-w-lg")}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-line">
              <h2 className="text-base font-semibold">{title}</h2>
              <button onClick={onClose} className="text-ink-subtle hover:text-ink p-1 rounded" aria-label="Fermer">
                <X size={16} />
              </button>
            </div>
            <div className="p-5">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; icon?: ReactNode }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="flex gap-1 border-b border-line px-3 overflow-x-auto" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "relative flex items-center gap-1.5 px-2.5 py-2.5 text-xs font-medium whitespace-nowrap transition-colors",
            value === t.id ? "text-ink" : "text-ink-subtle hover:text-ink-muted",
          )}
        >
          {t.icon}
          {t.label}
          {value === t.id && <motion.span layoutId="tab-underline" className="absolute left-1 right-1 -bottom-px h-0.5 bg-accent rounded-full" />}
        </button>
      ))}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-ink-muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "danger" | "warn" }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium text-ink-muted">{label}</div>
      <div className={cx("text-2xl font-semibold mt-1 tabular-nums", tone === "danger" && "text-red-400", tone === "warn" && "text-amber-300")}>{value}</div>
      {sub && <div className="text-xs text-ink-subtle mt-1">{sub}</div>}
    </Card>
  );
}

export function Gauge({ ratio, alert = 0.8, className }: { ratio: number; alert?: number; className?: string }) {
  const r = Math.max(0, Math.min(1, ratio || 0));
  const color = r >= 1 ? "bg-red-500" : r >= alert ? "bg-amber-400" : "bg-emerald-400";
  return (
    <div className={cx("relative h-1.5 w-full rounded-full bg-line-strong overflow-hidden", className)}>
      <div className={cx("h-full rounded-full transition-all duration-500", color)} style={{ width: `${r * 100}%` }} />
    </div>
  );
}
