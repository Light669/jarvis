// État partagé : vue d'ensemble + flux d'événements temps réel (WebSocket authentifié).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, getToken, type Overview } from "./api";

export interface LiveEvent {
  type: string;
  ts: string;
  [k: string]: any;
}

type Listener = (e: LiveEvent) => void;

interface Store {
  overview: Overview | null;
  refresh: () => Promise<void>;
  events: LiveEvent[];
  connected: boolean;
  subscribe: (fn: Listener) => () => void;
  reducedMotion: boolean;
  setReducedMotion: (v: boolean) => void;
  toast: (msg: string, kind?: "ok" | "err") => void;
  toasts: { id: number; msg: string; kind: "ok" | "err" }[];
}

const Ctx = createContext<Store | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [reducedMotion, setRM] = useState(
    () => localStorage.getItem("orchestra-reduced-motion") === "1" || window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [toasts, setToasts] = useState<Store["toasts"]>([]);
  const listeners = useRef(new Set<Listener>());
  const refreshTimer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      setOverview(await api<Overview>("/api/overview"));
    } catch {
      /* affiché par l'écran de connexion */
    }
  }, []);

  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current) return;
    refreshTimer.current = window.setTimeout(() => {
      refreshTimer.current = null;
      refresh();
    }, 250);
  }, [refresh]);

  useEffect(() => {
    refresh();
    let ws: WebSocket | null = null;
    let stop = false;
    let retry = 500;
    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(getToken())}`);
      ws.onopen = () => {
        setConnected(true);
        retry = 500;
        refresh();
      };
      ws.onclose = () => {
        setConnected(false);
        if (!stop) setTimeout(connect, (retry = Math.min(retry * 2, 8000)));
      };
      ws.onmessage = (m) => {
        const e: LiveEvent = JSON.parse(m.data);
        setEvents((prev) => [e, ...prev].slice(0, 300));
        listeners.current.forEach((fn) => fn(e));
        if (e.type !== "log") scheduleRefresh();
      };
    };
    connect();
    const poll = window.setInterval(refresh, 15000); // filet de sécurité
    return () => {
      stop = true;
      ws?.close();
      clearInterval(poll);
    };
  }, [refresh, scheduleRefresh]);

  const subscribe = useCallback((fn: Listener) => {
    listeners.current.add(fn);
    return () => void listeners.current.delete(fn);
  }, []);

  const setReducedMotion = (v: boolean) => {
    localStorage.setItem("orchestra-reduced-motion", v ? "1" : "0");
    setRM(v);
  };

  const toast = useCallback((msg: string, kind: "ok" | "err" = "ok") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, msg, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("reduce-motion", reducedMotion);
  }, [reducedMotion]);

  return (
    <Ctx.Provider value={{ overview, refresh, events, connected, subscribe, reducedMotion, setReducedMotion, toast, toasts }}>
      {children}
    </Ctx.Provider>
  );
}

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("StoreProvider manquant");
  return s;
}

/** Charge une ressource et la recharge quand `deps` changent ou sur événement temps réel filtré. */
export function useResource<T>(path: string | null, deps: unknown[] = [], reloadOn?: (e: LiveEvent) => boolean) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { subscribe } = useStore();
  const load = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (!reloadOn) return;
    let t: number | null = null;
    return subscribe((e) => {
      if (reloadOn(e) && !t) t = window.setTimeout(() => ((t = null), load()), 300);
    });
  }, [subscribe, load, reloadOn]);
  return { data, error, loading, reload: load, setData };
}
