import type { Metadata } from "next";
import { Inter, Poppins } from "next/font/google";
import "./globals.css";
import Sidebar from "./components/Sidebar";
import MobileNav from "./components/MobileNav";
import LiveStatusBar from "./components/LiveStatusBar";
import Footer from "./components/Footer";
import ServiceWorkerRegister from "./components/ServiceWorkerRegister";
import { ToastProvider } from "./components/ToastProvider";
import KeyboardShortcuts from "./components/KeyboardShortcuts";
import AuthGate from "./components/AuthGate";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
});
const poppins = Poppins({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-poppins",
});

export const metadata: Metadata = {
  title: "ATLAS by VECTA Sports — Commercial Intelligence",
  description:
    "One system. Every opportunity in global sport. ATLAS continuously scans the global sport ecosystem for payable opportunities, tenders and decision-makers, for VECTA Sports' commercial division.",
  manifest: "/manifest.json",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${poppins.variable}`}>
      <head>
        <script
          // Applies the saved theme before paint to avoid a flash of the wrong mode.
          dangerouslySetInnerHTML={{
            __html: `try{if(localStorage.getItem('atlas-theme')==='light'){document.documentElement.classList.add('light')}}catch(e){}`,
          }}
        />
      </head>
      <body>
        <AuthGate>
          <ToastProvider>
            <a href="#main-content" className="skip-link">
              Skip to main content
            </a>
            <div className="flex min-h-screen">
              <Sidebar />
              <div className="flex-1 flex flex-col min-w-0">
                <LiveStatusBar />
                <main
                  id="main-content"
                  tabIndex={-1}
                  className="flex-1 px-5 py-6 md:px-8 md:py-8 pb-24 md:pb-8 max-w-6xl mx-auto w-full"
                >
                  {children}
                </main>
                <Footer />
              </div>
            </div>
            <MobileNav />
            <KeyboardShortcuts />
          </ToastProvider>
          <ServiceWorkerRegister />
        </AuthGate>
      </body>
    </html>
  );
}
