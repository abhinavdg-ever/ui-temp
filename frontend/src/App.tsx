import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";
import LandingPage from "./LandingPage";
import FolderViewer from "./FolderViewer";
import LoginPage from "./LoginPage";

const AUTH_KEY = "advantmed_imaging_auth";

type Route =
  | { view: "landing" }
  | { view: "folder"; folderId: string };

function parsePath(pathname: string): Route {
  const match = pathname.match(/^\/folders\/([^/]+)\/?$/);
  if (match) {
    return { view: "folder", folderId: decodeURIComponent(match[1]) };
  }
  return { view: "landing" };
}

function pathFor(route: Route): string {
  if (route.view === "folder") {
    return `/folders/${encodeURIComponent(route.folderId)}`;
  }
  return "/";
}

function readAuth(): boolean {
  try {
    return sessionStorage.getItem(AUTH_KEY) === "1";
  } catch {
    return false;
  }
}

export default function App() {
  const [authed, setAuthed] = useState(readAuth);
  const [route, setRoute] = useState<Route>(() => parsePath(window.location.pathname));

  useEffect(() => {
    const onPop = () => setRoute(parsePath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  function navigate(next: Route) {
    const path = pathFor(next);
    if (path !== window.location.pathname) {
      window.history.pushState(null, "", path);
    }
    setRoute(next);
  }

  function handleLoginSuccess() {
    try {
      sessionStorage.setItem(AUTH_KEY, "1");
    } catch {
      /* ignore */
    }
    setAuthed(true);
  }

  function handleLogout() {
    try {
      sessionStorage.removeItem(AUTH_KEY);
    } catch {
      /* ignore */
    }
    setAuthed(false);
    navigate({ view: "landing" });
  }

  if (!authed) {
    return (
      <div className="shell shell-login">
        <LoginPage onSuccess={handleLoginSuccess} />
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <button
            type="button"
            className="brand-home"
            onClick={() => navigate({ view: "landing" })}
            aria-label="Go to home"
          >
            <img
              className="brand-wordmark"
              src="/advantmed-wordmark.svg"
              alt="Advantmed"
            />
          </button>
          <div>
            <strong>Document Processing AI</strong>
            <p>End to End Imaging Pipeline Results</p>
          </div>
        </div>
        <div className="topbar-meta">
          <span className="mode-pill">Local mode</span>
          <button type="button" className="logout-btn" onClick={handleLogout}>
            <LogOut size={14} aria-hidden="true" />
            Log out
          </button>
        </div>
      </header>
      <main className="main">
        {route.view === "landing" ? (
          <LandingPage onView={(folderId) => navigate({ view: "folder", folderId })} />
        ) : (
          <FolderViewer
            folderId={route.folderId}
            onBack={() => navigate({ view: "landing" })}
          />
        )}
      </main>
    </div>
  );
}
