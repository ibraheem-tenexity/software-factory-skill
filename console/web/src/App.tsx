import { useEffect, useState } from "react";
import { api, Me } from "./api";
import { MeProvider } from "./components/MeContext";
import { Dashboard } from "./components/Dashboard";
import { OrgAdminScreen } from "./components/OrgAdminScreen";
import { OnboardingScreen } from "./components/onboarding/OnboardingScreen";
import { LoginScreen } from "./components/LoginScreen";
import { FactoryConsole } from "./components/factory/FactoryConsole";
import { ProjectView } from "./components/project/ProjectView";

function readInitialProject(): string | null {
  return new URLSearchParams(location.search).get("run");
}

function readInitialView(): "project" | "factory" {
  return new URLSearchParams(location.search).get("view") === "factory" ? "factory" : "project";
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
  // Open-run peer view (§2.5): 'project' = ProjectView (Overview/Documents tabs); 'factory' = the
  // Factory Console. The "Factory console" peer-tab flips this; FactoryConsole's back returns here.
  const [openView, setOpenView] = useState<"project" | "factory">(readInitialView());

  const syncUrl = (run: string | null) => {
    const p = new URLSearchParams();
    if (run) p.set("run", run);
    history.replaceState(null, "", "?" + p.toString());
  };

  // Sync openView → ?view= without clobbering ?run=
  useEffect(() => {
    const p = new URLSearchParams(location.search);
    if (openView === "factory") p.set("view", "factory"); else p.delete("view");
    history.replaceState(null, "", "?" + p.toString());
  }, [openView]);

  // Sync showOrg → ?screen=org (SOF-220), same pattern as openView above.
  useEffect(() => {
    const p = new URLSearchParams(location.search);
    if (showOrg) p.set("screen", "org"); else p.delete("screen");
    history.replaceState(null, "", "?" + p.toString());
  }, [showOrg]);

  const openProject = (id: string) => { setProjectId(id); setShowProjects(false); setShowOnboarding(false); setOpenView("project"); syncUrl(id); };
  const backToProjects = () => { setProjectId(null); setShowProjects(true); syncUrl(null); };

  // keep the SPA boot warm — discover runs once so a deep-linked ?run= resolves.
  useEffect(() => { if (!projectId) api.projects().catch(() => {}); }, [projectId]);

  if (showOnboarding) {
    return <OnboardingScreen resumeProjectId={resumeProjectId} onComplete={(id) => { setResumeProjectId(null); openProject(id); }} onBack={() => { setShowOnboarding(false); setResumeProjectId(null); setShowProjects(true); syncUrl(null); }} />;
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

  // Open run ⇒ the §2.5 Project View (Overview/Documents tabs) is the default; its "Factory console"
  // peer-tab flips to the Factory Console (PRD §2.6), whose back returns to the Project View.
  if (openView === "factory") {
    // The console's peer-tab strip navigates back to the ProjectView with the chosen tab: seed the
    // ?tab= param (ProjectView reads it on mount) then flip the open view.
    const switchTab = (tab: "overview" | "documents") => {
      const p = new URLSearchParams(location.search);
      if (tab === "overview") p.delete("tab"); else p.set("tab", tab);
      history.replaceState(null, "", "?" + p.toString());
      setOpenView("project");
    };
    return <FactoryConsole projectId={projectId} onBack={() => setOpenView("project")} onSwitchTab={switchTab} />;
  }
  return <ProjectView projectId={projectId} onBack={backToProjects} onOpenFactory={() => setOpenView("factory")}
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
