// Ana Dashboard sayfası
"use client";

import { useState, useCallback } from "react";
import { api } from "@/lib/api";
import type { AgentStatus, PendingAction, PendingComment, ActionHistory } from "@/lib/types";
import { usePolling } from "@/hooks/usePolling";
import { useToast, ToastContainer } from "@/components/Toast";
import Header from "@/components/Header";
import StatsGrid from "@/components/StatsGrid";
import ActionCard from "@/components/ActionCard";
import CommentCard from "@/components/CommentCard";
import HistoryTable from "@/components/HistoryTable";
import TriggerGrid from "@/components/TriggerGrid";
import styles from "./page.module.css";

type TabName = "actions" | "comments" | "history" | "trigger";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabName>("actions");
  const [refreshInterval, setRefreshInterval] = useState(10000);
  const { toasts, show: showToast } = useToast();

  // Veri çekme (polling)
  const fetchStatus = useCallback(() => api.getStatus(), []);
  const fetchActions = useCallback(() => api.getPendingActions(), []);
  const fetchComments = useCallback(() => api.getPendingComments(), []);
  const fetchHistory = useCallback(() => api.getActions(25), []);

  const { data: statusData } = usePolling<AgentStatus>(fetchStatus, refreshInterval);
  const { data: pendingActions, refetch: refetchActions } = usePolling<PendingAction[]>(fetchActions, refreshInterval);
  const { data: pendingComments, refetch: refetchComments } = usePolling<PendingComment[]>(fetchComments, refreshInterval);
  const { data: historyActions } = usePolling<ActionHistory[]>(fetchHistory, refreshInterval);

  const actionCount = pendingActions?.length ?? 0;
  const commentCount = pendingComments?.length ?? 0;

  const tabs: { key: TabName; label: string; badge?: number }[] = [
    { key: "actions", label: "⏳ Kod Değişiklikleri", badge: actionCount },
    { key: "comments", label: "💬 Yorumlar", badge: commentCount },
    { key: "history", label: "📜 Geçmiş" },
    { key: "trigger", label: "🚀 Tetikle" },
  ];

  return (
    <>
      <Header
        status={statusData?.status || ""}
        refreshInterval={refreshInterval}
        onRefreshChange={setRefreshInterval}
      />

      <div className={styles.container}>
        <StatsGrid stats={statusData?.stats || null} />

        {/* Tab Menüsü */}
        <div className={styles.tabs}>
          {tabs.map((tab) => (
            <button
              key={tab.key}
              className={`${styles.tab} ${activeTab === tab.key ? styles.tabActive : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
              {tab.badge !== undefined && tab.badge > 0 && (
                <span className={styles.badge}>{tab.badge}</span>
              )}
            </button>
          ))}
        </div>

        {/* Tab İçerikleri */}
        {activeTab === "actions" && (
          <div className={styles.tabPanel}>
            {actionCount === 0 ? (
              <div className={styles.empty}>
                <div className={styles.emptyEmoji}>✨</div>
                <p>Onay bekleyen kod değişikliği yok</p>
              </div>
            ) : (
              pendingActions?.map((action) => (
                <ActionCard
                  key={action.id}
                  action={action}
                  onToast={showToast}
                  onRefresh={refetchActions}
                />
              ))
            )}
          </div>
        )}

        {activeTab === "comments" && (
          <div className={styles.tabPanel}>
            {commentCount === 0 ? (
              <div className={styles.empty}>
                <div className={styles.emptyEmoji}>✨</div>
                <p>Onay bekleyen yorum yok</p>
              </div>
            ) : (
              pendingComments?.map((comment) => (
                <CommentCard
                  key={comment.id}
                  comment={comment}
                  onToast={showToast}
                  onRefresh={refetchComments}
                />
              ))
            )}
          </div>
        )}

        {activeTab === "history" && (
          <div className={styles.tabPanel}>
            <HistoryTable actions={historyActions} />
          </div>
        )}

        {activeTab === "trigger" && (
          <div className={styles.tabPanel}>
            <TriggerGrid onToast={showToast} />
          </div>
        )}
      </div>

      <ToastContainer toasts={toasts} />
    </>
  );
}
