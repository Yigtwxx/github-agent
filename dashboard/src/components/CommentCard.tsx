// Onay bekleyen yorum kartı
"use client";

import { useState } from "react";
import type { PendingComment } from "@/lib/types";
import { api } from "@/lib/api";
import type { ToastType } from "./Toast";
import styles from "./CommentCard.module.css";

interface CommentCardProps {
    comment: PendingComment;
    onToast: (message: string, type: ToastType) => void;
    onRefresh: () => void;
}

export default function CommentCard({ comment, onToast, onRefresh }: CommentCardProps) {
    const [loading, setLoading] = useState(false);

    const handleApprove = async () => {
        setLoading(true);
        const res = await api.approveComment(comment.id);
        if (res && !("error" in res)) {
            onToast(`Yorum #${comment.id} onaylandı! GitHub'a gönderiliyor.`, "success");
            setTimeout(onRefresh, 1000);
        } else {
            onToast("Hata oluştu", "error");
            setLoading(false);
        }
    };

    const handleReject = async () => {
        setLoading(true);
        const res = await api.rejectComment(comment.id);
        if (res && !("error" in res)) {
            onToast(`Yorum #${comment.id} reddedildi.`, "info");
            setTimeout(onRefresh, 500);
        } else {
            onToast("Hata oluştu", "error");
            setLoading(false);
        }
    };

    const typeEmoji = comment.type === "ISSUE" ? "🐛" : "🗣️";

    return (
        <div className={styles.card}>
            <div className={styles.header}>
                <div>
                    <span className={styles.id}>#{comment.id}</span>
                    <div className={styles.meta}>
                        <span>📦 {comment.repo}</span>
                        <span>{typeEmoji} {comment.type} #{comment.target_number}</span>
                        {comment.target_url && (
                            <a href={comment.target_url} target="_blank" rel="noopener noreferrer">
                                🔗 GitHub&apos;da Aç
                            </a>
                        )}
                    </div>
                </div>
                <div className={styles.buttons}>
                    <button className={styles.btnApprove} onClick={handleApprove} disabled={loading}>
                        ✅ Onayla &amp; Gönder
                    </button>
                    <button className={styles.btnReject} onClick={handleReject} disabled={loading}>
                        ❌ Reddet
                    </button>
                </div>
            </div>
            <div className={styles.body}>{comment.body_preview}</div>
        </div>
    );
}
