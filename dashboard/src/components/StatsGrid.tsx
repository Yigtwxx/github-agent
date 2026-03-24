// İstatistik kartları grid bileşeni
"use client";

import type { AgentStats } from "@/lib/types";
import styles from "./StatsGrid.module.css";

const STAT_ITEMS: { key: keyof AgentStats; emoji: string; label: string }[] = [
    { key: "cycles_completed", emoji: "🔄", label: "Döngü" },
    { key: "repos_discovered", emoji: "📦", label: "Repo Keşfi" },
    { key: "issues_analyzed", emoji: "🔍", label: "Issue Analizi" },
    { key: "discussions_analyzed", emoji: "🗣️", label: "Discussion" },
    { key: "comments_generated", emoji: "💬", label: "Yorum Üretimi" },
    { key: "prs_created", emoji: "🚀", label: "PR Oluşturma" },
];

interface StatsGridProps {
    stats: AgentStats | null;
}

export default function StatsGrid({ stats }: StatsGridProps) {
    return (
        <div className={styles.grid}>
            {STAT_ITEMS.map(({ key, emoji, label }) => (
                <div key={key} className={styles.card}>
                    <div className={styles.emoji}>{emoji}</div>
                    <div className={styles.value}>{stats?.[key] ?? "-"}</div>
                    <div className={styles.label}>{label}</div>
                </div>
            ))}
        </div>
    );
}
