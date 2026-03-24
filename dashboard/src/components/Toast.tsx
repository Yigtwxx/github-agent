// Toast bildirim bileşeni
"use client";

import { useState, useCallback } from "react";
import styles from "./Toast.module.css";

export type ToastType = "success" | "error" | "info";

interface Toast {
    id: number;
    message: string;
    type: ToastType;
}

let toastId = 0;

export function useToast() {
    const [toasts, setToasts] = useState<Toast[]>([]);

    const show = useCallback((message: string, type: ToastType = "info") => {
        const id = ++toastId;
        setToasts((prev) => [...prev, { id, message, type }]);
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 4000);
    }, []);

    return { toasts, show };
}

export function ToastContainer({ toasts }: { toasts: Toast[] }) {
    return (
        <div className={styles.container}>
            {toasts.map((t) => (
                <div key={t.id} className={`${styles.toast} ${styles[t.type]}`}>
                    {t.message}
                </div>
            ))}
        </div>
    );
}
