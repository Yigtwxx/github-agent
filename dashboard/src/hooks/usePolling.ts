// Custom hook: polling ile veri çekme
"use client";

import { useState, useEffect, useCallback } from "react";

export function usePolling<T>(
    fetcher: () => Promise<T | null>,
    intervalMs: number = 10000
): { data: T | null; loading: boolean; refetch: () => void } {
    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState(true);

    const refetch = useCallback(async () => {
        const result = await fetcher();
        setData(result);
        setLoading(false);
    }, [fetcher]);

    useEffect(() => {
        let mounted = true;
        // The first update is run asynchronously to avoid React's setState inside effect warning
        void Promise.resolve().then(() => {
            if (mounted) refetch();
        });

        if (intervalMs <= 0) return;
        const timer = setInterval(() => {
            if (mounted) refetch();
        }, intervalMs);

        return () => {
            mounted = false;
            clearInterval(timer);
        };
    }, [refetch, intervalMs]);

    return { data, loading, refetch };
}
