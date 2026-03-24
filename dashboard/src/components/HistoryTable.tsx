// Aksiyon geçmişi tablosu
"use client";

import type { ActionHistory } from "@/lib/types";
import styles from "./HistoryTable.module.css";

const STATUS_COLORS: Record<string, string> = {
    SUCCESS: "green",
    FAILED: "red",
    AWAITING_APPROVAL: "yellow",
    APPROVED: "blue",
    REJECTED: "red",
    IN_PROGRESS: "cyan",
    POSTED: "purple",
};

interface HistoryTableProps {
    actions: ActionHistory[] | null;
}

export default function HistoryTable({ actions }: HistoryTableProps) {
    if (!actions || actions.length === 0) {
        return (
            <div className={styles.empty}>
                <div className={styles.emptyEmoji}>📜</div>
                <p>Henüz aksiyon geçmişi yok</p>
            </div>
        );
    }

    return (
        <div className={styles.tableWrap}>
            <table className={styles.table}>
                <thead>
                    <tr>
                        <th>#</th>
                        <th>Repo</th>
                        <th>Tip</th>
                        <th>Durum</th>
                        <th>PR</th>
                        <th>Tarih</th>
                    </tr>
                </thead>
                <tbody>
                    {actions.map((a) => (
                        <tr key={a.id}>
                            <td className={styles.idCol}>{a.id}</td>
                            <td className={styles.repoCol}>{a.repo}</td>
                            <td>{a.action_type}</td>
                            <td>
                                <span className={`${styles.tag} ${styles[`tag${STATUS_COLORS[a.status] || "default"}`]}`}>
                                    {a.status}
                                </span>
                            </td>
                            <td>
                                {a.pr_url ? (
                                    <a href={a.pr_url} target="_blank" rel="noopener noreferrer">PR ↗</a>
                                ) : "-"}
                            </td>
                            <td className={styles.dateCol}>{(a.created_at || "").substring(0, 16)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
