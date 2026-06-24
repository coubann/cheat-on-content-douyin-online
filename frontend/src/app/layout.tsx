import type { Metadata } from "next";
import "@/styles/globals.css";
import Sidebar from "@/components/Sidebar";
import { AuthProvider } from "@/lib/auth-context";
import AuthGuard from "@/components/AuthGuard";

export const metadata: Metadata = {
  title: "Content Studio — 爆款预测系统",
  description: "基于 cheat-on-content 的内容作弊系统，预测你的内容火不火",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen" style={{ background: "var(--bg-primary)" }}>
        <AuthProvider>
          <AuthGuard>
            <div className="flex min-h-screen">
              <Sidebar />
              <main className="md:ml-56 pt-14 md:pt-0 flex-1 p-6">
                {children}
              </main>
            </div>
          </AuthGuard>
        </AuthProvider>
      </body>
    </html>
  );
}
