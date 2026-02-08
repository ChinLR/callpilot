import { Link } from "react-router-dom";
import { ArrowRight, Play } from "lucide-react";
import callpilotLogo from "@/assets/callpilot-logo.png";

const LandingPage = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="border-b border-primary/15">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <img src={callpilotLogo} alt="CallPilot" className="h-8 w-8 rounded-lg" />
            <span className="text-lg font-bold tracking-tight font-display uppercase">
              CallPilot
            </span>
          </div>
          <nav className="flex items-center gap-8">
            <a
              href="#how-it-works"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              How it works
            </a>
            <a
              href="#pricing"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Pricing
            </a>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <main className="mx-auto max-w-5xl px-6">
        <div className="flex flex-col items-start justify-center pt-24 pb-32 sm:pt-36 sm:pb-44">
          {/* Label */}
          <div className="mb-8 flex items-center gap-2.5 rounded-full border border-primary/30 bg-primary/5 px-4 py-1.5">
            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
            <span className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Voice AI Agent
            </span>
          </div>

          {/* Heading */}
          <h1 className="font-serif text-5xl leading-[1.1] tracking-tight sm:text-7xl md:text-8xl">
            We make the calls
            <br />
            <em className="text-primary italic">
              so you don't have to
            </em>
          </h1>

          {/* Subtitle */}
          <p className="mt-6 max-w-lg text-lg leading-relaxed text-muted-foreground sm:text-xl">
            CallPilot uses voice AI to phone providers, find available
            appointments, and book the best slot for you — hands-free.
          </p>

          {/* CTAs */}
          <div className="mt-10 flex items-center gap-6">
            <Link
              to="/book"
              className="group inline-flex items-center gap-2.5 rounded-full bg-primary px-7 py-3.5 text-sm font-semibold text-primary-foreground transition-all hover:bg-primary/90 hover:shadow-[0_0_30px_hsl(40,72%,52%,0.25)]"
            >
              Start a campaign
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <button className="inline-flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground">
              <Play className="h-4 w-4" />
              Watch demo
            </button>
          </div>
        </div>
      </main>

      {/* Accent line */}
      <div className="h-px bg-gradient-to-r from-transparent via-primary/40 to-transparent" />
    </div>
  );
};

export default LandingPage;
