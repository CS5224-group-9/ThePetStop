"use client";
import { useEffect, useState } from "react";
export function useResource<T>(key: string, loader: () => Promise<T>) {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    data: T | null;
    error: string | null;
    loading: boolean;
  }>({ key, data: null, error: null, loading: true });
  useEffect(() => {
    let current = true;
    queueMicrotask(() => {
      if (current) setResult({ key, data: null, error: null, loading: true });
    });
    loader()
      .then((data) => {
        if (current) setResult({ key, data, error: null, loading: false });
      })
      .catch((error) => {
        if (current)
          setResult({
            key,
            data: null,
            error:
              error instanceof Error
                ? error.message
                : "Unable to load this content.",
            loading: false,
          });
      });
    return () => {
      current = false;
    };
  }, [key, loader, revision]);
  return {
    ...(result.key === key
      ? result
      : { key, data: null, error: null, loading: true }),
    reload: () => setRevision((v) => v + 1),
  };
}
