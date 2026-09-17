import { useEffect, useState } from "react";

/**
 * Load a demo's dataset on demand.
 *
 * The price file alone is ~600 KB. Importing it statically would put it in the
 * initial bundle for every visitor, including the ones who never open a demo.
 * A dynamic import makes Vite emit it as a separate chunk fetched on first use.
 */
export function useDemoData<T>(load: () => Promise<{ default: T }>): T | null {
  const [data, setData] = useState<T | null>(null);

  useEffect(() => {
    let alive = true;
    void load().then((module) => {
      if (alive) setData(module.default);
    });
    return () => {
      alive = false;
    };
    // The loader is a stable module-level function at every call site.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return data;
}

export function DemoLoading() {
  return null;
}
