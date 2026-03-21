// Onay bekleyen kod değişikliği kartı
"use client";

import { useState } from "react";
import type { PendingAction } from "@/lib/types";
import { api } from "@/lib/api";
import type { ToastType } from "./Toast";
import styles from "./ActionCard.module.css";

interface ActionCardProps {
    action: PendingAction;
    onToast: (message: string, type: ToastType) => void;
    onRefresh: () => void;
}

export default function ActionCard({ action, onToast, onRefresh }: ActionCardProps) {
    const [loading, setLoading] = useState(false);
    const [expanded, setExpanded] = useState(false);
    const details = action.details as Record<string, unknown> | null;

    const handleApprove = async () => {
        setLoading(true);
        const res = await api.approveAction(action.id);
        if (res && !("error" in res)) {
            onToast(`Aksiyon #${action.id} onaylandı! PR süreci başlatılıyor.`, "success");
            setTimeout(onRefresh, 1000);
        } else {
            onToast("Hata oluştu", "error");
            setLoading(false);
        }
    };

    const handleReject = async () => {
        setLoading(true);
        const res = await api.rejectAction(action.id);
        if (res && !("error" in res)) {
            onToast(`Aksiyon #${action.id} reddedildi.`, "info");
            setTimeout(onRefresh, 500);
        } else {
            onToast("Hata oluştu", "error");
            setLoading(false);
        }
    };

    return (
        <div className={styles.card}>
            <div className={styles.header}>
                <div>
                    <span className={styles.id}>#{action.id}</span>
                    <div className={styles.meta}>
                        <span>📦 {action.repo}</span>
                        <span>🌿 {action.branch || "N/A"}</span>
                        {action.sandbox_test !== null && (
                            <span>{action.sandbox_test ? "✅" : "❌"} Sandbox</span>
                        )}
                        {!!details?.difficulty && (
                            <span>🎯 Zorluk: {String(details.difficulty)}/10</span>
                        )}
                    </div>
                </div>
                <div className={styles.buttons}>
                    <button
                        className={styles.btnApprove}
                        onClick={handleApprove}
                        disabled={loading}
                    >
                        ✅ Onayla
                    </button>
                    <button
                        className={styles.btnReject}
                        onClick={handleReject}
                        disabled={loading}
                    >
                        ❌ Reddet
                    </button>
                </div>
            </div>

            <div className={styles.commitMsg}>
                <strong>Commit:</strong> {action.commit_message || "N/A"}
            </div>

            {!!details?.changes_summary && (
                <div className={styles.summary}>{String(details.changes_summary)}</div>
            )}

            {action.patches.length > 0 && (
                <>
                    <button
                        className={styles.expandBtn}
                        onClick={() => setExpanded(!expanded)}
                    >
                        {expanded ? "▲ Kodu Gizle" : `▼ Kodu Göster (${action.patches.length} dosya)`}
                    </button>

                    {expanded && (
                        <div className={styles.patches}>
                            {action.patches.map((p, i) => (
                                <div key={i} className={styles.patch}>
                                    <div className={styles.fileName}>📄 {p.file}</div>
                                    {p.diff && <div className={styles.diffText}>{p.diff}</div>}
                                    {p.content_preview && (
                                        <pre className={styles.codeBlock}>{p.content_preview}</pre>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </div>
    );
}
