// Header bileşeni
"use client";

import styles from "./Header.module.css";

interface HeaderProps {
    status: string;
    refreshInterval: number;
    onRefreshChange: (seconds: number) => void;
}

export default function Header({ status, refreshInterval, onRefreshChange }: HeaderProps) {
    const dotClass = status.toLowerCase().replace(/[^a-z]/g, "");

    return (
        <header className={styles.header}>
            <div className={styles.left}>
                <span className={styles.logo}>🤖</span>
                <h1 className={styles.title}>GitHub AI Agent</h1>
                <span className={styles.badge}>
                    <span className={`${styles.dot} ${styles[dotClass] || styles.idle}`} />
                    <span>{status || "Bağlanıyor..."}</span>
                </span>
            </div>
            <div className={styles.refresh}>
                <span>Otomatik yenile:</span>
                <select
                    value={refreshInterval}
                    onChange={(e) => onRefreshChange(Number(e.target.value))}
                >
                    <option value={5000}>5s</option>
                    <option value={10000}>10s</option>
                    <option value={30000}>30s</option>
                    <option value={0}>Kapalı</option>
                </select>
            </div>
        </header>
    );
}
