// Manuel görev tetikleme grid bileşeni
"use client";

import { useState } from "react";
import type { TaskType } from "@/lib/types";
import { api } from "@/lib/api";
import type { ToastType } from "./Toast";
import styles from "./TriggerGrid.module.css";

interface TaskItem {
    type: TaskType;
    emoji: string;
    title: string;
    desc: string;
}

const TASKS: TaskItem[] = [
    { type: "trend_hunt", emoji: "🔍", title: "Trend Avcısı", desc: "Popüler repoları keşfet (5 dilde)" },
    { type: "repo_setup", emoji: "📚", title: "Repo Kurulum", desc: "Klonla + RAG indeksle" },
    { type: "community_support", emoji: "💬", title: "Community Support", desc: "Issue'lara AI cevabı üret" },
    { type: "discussion_support", emoji: "🗣️", title: "Discussion Support", desc: "Discussion'lara AI cevabı üret" },
    { type: "issue_solving", emoji: "🔧", title: "Issue Solver", desc: "Çözülebilir issue bul + kod üret" },
];

interface TriggerGridProps {
    onToast: (msg: string, type: ToastType) => void;
}

export default function TriggerGrid({ onToast }: TriggerGridProps) {
    const [triggered, setTriggered] = useState<string | null>(null);

    const handleTrigger = async (task: TaskItem) => {
        setTriggered(task.type);
        const res = await api.triggerTask(task.type);
        if (res && !("error" in res)) {
            onToast(`'${task.title}' görevi tetiklendi!`, "success");
        } else {
            onToast("Hata oluştu", "error");
        }
        setTimeout(() => setTriggered(null), 3000);
    };

    return (
        <div className={styles.grid}>
            {TASKS.map((task) => (
                <button
                    key={task.type}
                    className={`${styles.card} ${triggered === task.type ? styles.triggered : ""}`}
                    onClick={() => handleTrigger(task)}
                >
                    <div className={styles.emoji}>{task.emoji}</div>
                    <div className={styles.title}>{task.title}</div>
                    <div className={styles.desc}>{task.desc}</div>
                </button>
            ))}
        </div>
    );
}
