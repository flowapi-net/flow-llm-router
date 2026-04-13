import type { Metadata } from "next";
import Link from "next/link";
import VaultGate from "@/components/VaultGate";
import "./globals.css";

export const metadata: Metadata = {
  title: "FlowGate Dashboard",
  description: "Local-first LLM gateway with token usage analytics",
};

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="px-3 py-2 rounded-md text-sm font-medium text-gray-300 hover:bg-gray-700 hover:text-white transition-colors"
    >
      {children}
    </Link>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <VaultGate>
          <nav className="bg-gray-900 border-b border-gray-800">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex items-center justify-between h-14">
                <div className="flex items-center gap-1">
                  <Link href="/" className="text-white font-bold text-lg tracking-tight mr-6">
                    ⚡ FlowGate
                  </Link>
                  <NavLink href="/">Dashboard</NavLink>
                  <NavLink href="/logs/">Logs</NavLink>
                  <NavLink href="/analytics/">Analytics</NavLink>
                  <NavLink href="/providers/">Providers</NavLink>
                  <NavLink href="/models/">Models</NavLink>
                  <NavLink href="/router/">Router</NavLink>
                  <NavLink href="/integrate/">API</NavLink>
                  <NavLink href="/settings/">Settings</NavLink>
                </div>
                <div className="text-gray-500 text-xs">v0.1.0</div>
              </div>
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
            {children}
          </main>
        </VaultGate>
      </body>
    </html>
  );
}
