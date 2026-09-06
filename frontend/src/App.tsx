import { useEffect, useState } from "react";
import LandingPage from "./LandingPage";
import FolderViewer from "./FolderViewer";

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

export default function App() {
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
            <img className="brand-mark" src="/advantmed-logo.png" alt="Advantmed" />
          </button>
          <div>
            <strong>Advantmed - Document Processing AI</strong>
            <p>End to End Imaging Pipeline Results</p>
          </div>
        </div>
        <div className="topbar-meta">
          <span className="mode-pill">Local mode</span>
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
