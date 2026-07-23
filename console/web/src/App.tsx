import { useEffect, useState } from "react";
import { api, Me } from "./api";
import { MeProvider } from "./components/MeContext";
import { Dashboard } from "./components/Dashboard";
import { OrgAdminScreen } from "./components/OrgAdminScreen";
import { OnboardingScreen } from "./components/onboarding/OnboardingScreen";
import { LoginScreen } from "./components/LoginScreen";
import { ProjectConsole } from "./components/project/ProjectConsole";

function readInitialProject(): string | null {
  return new URLSearchParams(location.search).get("run");
}

function readInitialShowOrg(): boolean {
  return new URLSearchParams(location.search).get("screen") === "org";
}

export function App() {
  const [projectId, setProjectId] = useState<string | null>(readInitialProject());
  const [showProjects, setShowProjects] = useState<boolean>(!readInitialProject());
  // The Option C onboarding is the "new project" front door (shown instead of an empty build console).
  const [showOnboarding, setShowOnboarding] = useState<boolean>(false);
  // Resuming an existing draft (project-view "Complete setup & start building"): the onboarding adopts
  // this draft id instead of minting a new one, and rehydrates its fields from GET /draft. null = fresh.
  const [resumeProjectId, setResumeProjectId] = useState<string | null>(null);
  // Org admin route (dashboard org switcher / "Manage organization →"), synced to ?screen=org
  // (SOF-220) so a reload while in Org Admin doesn't drop back to the Dashboard.
  const [showOrg, setShowOrg] = useState<boolean>(readInitialShowOrg());
  const syncUrl = (run: string | null) => {
    const p = new URLSearchParams();
    if (run) p.set("run", run);
    history.replaceState(null, "", "?" + p.toString());
  };

  // Sync showOrg → ?screen=org (SOF-220).
  useEffect(() => {
    const p = new URLSearchParams(location.search);
    if (showOrg) p.set("screen", "org"); else p.delete("screen");
    history.replaceState(null, "", "?" + p.toString());
  }, [showOrg]);

  // Open a run in the unified Project Console shell. `initialView` deep-links a peer (a fresh
  // handoff lands on the Factory console per §2.4a); the shell reads ?view on mount.
  const openProject = (id: string, initialView?: string) => {
    setProjectId(id); setShowProjects(false); setShowOnboarding(false);
    const p = new URLSearchParams();
    p.set("run", id);
    if (initialView && initialView !== "overview") p.set("view", initialView);
    history.replaceState(null, "", "?" + p.toString());
  };
  const backToProjects = () => { setProjectId(null); setShowProjects(true); syncUrl(null); };

  // keep the SPA boot warm — discover runs once so a deep-linked ?run= resolves.
  useEffect(() => { if (!projectId) api.projects().catch(() => {}); }, [projectId]);

  if (showOnboarding) {
    return <OnboardingScreen resumeProjectId={resumeProjectId} onComplete={(id) => { setResumeProjectId(null); openProject(id, "factory"); }} onBack={() => { setShowOnboarding(false); setResumeProjectId(null); setShowProjects(true); syncUrl(null); }} />;
  }

  if (showOrg) {
    return <OrgAdminScreen onBack={() => setShowOrg(false)} />;
  }

  if (showProjects || !projectId) {
    // Projects dashboard (PRD §2.2) is the post-login home. onOpen reuses openProject (into the
    // Factory Console — the open-run view below); onNew → onboarding; onOrg → §2.3 placeholder.
    return (
      <Dashboard
        onOpen={openProject}
        onNew={() => { setResumeProjectId(null); setProjectId(null); setShowProjects(false); setShowOnboarding(true); }}
        onOrg={() => setShowOrg(true)}
      />
    );
  }

  // Open run ⇒ the ONE unified Project Console shell (§2.5): Overview · Product brief · Factory
  // outputs · Factory console · Files [· Maintenance]. The shell owns ?view=<peer> internally.
  return <ProjectConsole projectId={projectId} onBack={backToProjects}
    onResume={() => { setResumeProjectId(projectId); setShowProjects(false); setShowOnboarding(true); }} onOpen={openProject} />;
}

// ── Auth gate (Option B) ───────────────────────────────────────────────────────────────────
// Top-level seam the whole React track gates through. Reads the public /api/auth/config: auth
// off (dev/test) ⇒ straight to the app; auth on ⇒ check /api/me FIRST and short-circuit to
// <LoginScreen> on 401, BEFORE App mounts and fires its data fetches. On Google success the
// gate re-resolves (cookie now set ⇒ /api/me 200 ⇒ app).
type GateState = "loading" | "login" | "app";

export function Gate() {
  const [state, setState] = useState<GateState>("loading");
  const [clientId, setClientId] = useState("");
  const [me, setMe] = useState<Me | null>(null);

  const resolve = () => {
    api.authConfig()
      .then((cfg) => {
        if (!cfg.enabled) { setState("app"); return; }   // auth off ⇒ open console (no login)
        setClientId(cfg.client_id);
        api.me().then((data) => { setMe(data); setState("app"); }).catch(() => setState("login"));  // 401 ⇒ login
      })
      .catch(() => setState("app"));   // config unreachable ⇒ fail open, don't lock the user out
  };

  useEffect(resolve, []);

  // Any in-app API call that gets 401 (expired session) fires sf:auth-expired.
  // Re-running resolve() re-checks /api/me → if still 401 → setState("login").
  useEffect(() => {
    const onExpired = () => resolve();
    window.addEventListener("sf:auth-expired", onExpired);
    return () => window.removeEventListener("sf:auth-expired", onExpired);
  }, []);

  if (state === "loading") return <div style={{ height: "100vh", background: "#FAFAFA" }} />;
  if (state === "login") return <LoginScreen clientId={clientId} onAuthed={resolve} />;
  return <MeProvider initial={me}><App /></MeProvider>;
}
