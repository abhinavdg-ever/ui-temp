import { useEffect, useState } from "react";
import LandingPage from "./LandingPage";
import FolderViewer from "./FolderViewer";
import FileViewer from "./FileViewer";
import LoginPage from "./LoginPage";
import UserProfileMenu from "./UserProfileMenu";

const AUTH_KEY = "advantmed_imaging_auth";

type Route =
  | { view: "landing" }
  | { view: "folder"; folderId: string }
  | { view: "file-viewer"; folderId?: string };

function parsePath(pathname: string): Route {
  const fileMatch = pathname.match(/^\/file-viewer(?:\/([^/]+))?\/?$/);
  if (fileMatch) {
    return {
      view: "file-viewer",
      folderId: fileMatch[1] ? decodeURIComponent(fileMatch[1]) : undefined,
    };
  }
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
  if (route.view === "file-viewer") {
    return route.folderId
      ? `/file-viewer/${encodeURIComponent(route.folderId)}`
      : "/file-viewer";
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
          <UserProfileMenu
            displayName="imaging-user"
            initials="IU"
            currentView={route.view}
            onOpenFileViewer={() => navigate({ view: "file-viewer" })}
            onOpenHistory={() => navigate({ view: "landing" })}
            onLogout={handleLogout}
          />
        </div>
      </header>
      <main className="main">
        {route.view === "landing" ? (
          <LandingPage
            onView={(folderId) => navigate({ view: "folder", folderId })}
            onOpenFileViewer={() => navigate({ view: "file-viewer" })}
          />
        ) : route.view === "file-viewer" ? (
          <FileViewer
            initialFolderId={route.folderId ?? null}
            onBack={() => navigate({ view: "landing" })}
          />
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
