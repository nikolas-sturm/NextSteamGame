import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, Manrope } from "next/font/google";
import "./globals.css";
import "./contract.css";
const display = Fraunces({ subsets:["latin"], variable:"--font-display" });
const body = Manrope({ subsets:["latin"], variable:"--font-body" });
const mono = IBM_Plex_Mono({ subsets:["latin"], weight:["400","600"], variable:"--font-mono" });
export const metadata: Metadata = { title:"Signal & Steam | Find your next game", description:"Recommendations shaped by what you want to feel and do next." };
export default function RootLayout({ children }: LayoutProps<"/">) { return <html lang="en" className={`${display.variable} ${body.variable} ${mono.variable}`}><body>{children}</body></html>; }
