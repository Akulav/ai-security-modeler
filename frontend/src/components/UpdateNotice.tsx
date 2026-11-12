import { Download, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type UpdateStatus } from "../api";

const BUSY = ["checking", "downloading", "installing"];

/** The app's own updates: the desktop launcher checks GitHub and installs; this shows it and asks it to. */
export default function UpdateNotice() {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [asked, setAsked] = useState<"" | "check" | "install">("");

  const refresh = useCallback(() => {
    api.updateStatus().then(setStatus).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const busy = asked !== "" || BUSY.includes(status?.state ?? "");
    const timer = window.setInterval(refresh, busy ? 2000 : 60000);
    return () => window.clearInterval(timer);
  }, [refresh, asked, status?.state]);

  useEffect(() => {
    if (asked === "check" && status && !BUSY.includes(status.state)) setAsked("");
    if (asked === "install" && status?.state === "update failed") setAsked("");
  }, [asked, status]);

  if (!status?.managed) return null;

  if (asked === "install" || status.state === "downloading" || status.state === "installing") {
    return <div className="update-notice busy"><RefreshCw size={13} className="spin" /> Updating to v{status.latest}: the app restarts by itself</div>;
  }
  if (status.newer) {
    return (
      <div className="update-notice">
        <button
          type="button"
          className="btn primary small"
          title={status.notes || `Version ${status.latest} is available`}
          onClick={() => { setAsked("install"); api.installUpdate().catch(() => setAsked("")); }}
        >
          <Download size={13} /> Update to v{status.latest}
        </button>
        {status.page && <a href={status.page} target="_blank" rel="noopener noreferrer">What's new</a>}
      </div>
    );
  }
  const checking = asked === "check" || status.state === "checking";
  return (
    <div className="update-notice quiet">
      <button type="button" className="link" disabled={checking}
        onClick={() => { setAsked("check"); api.checkUpdate().catch(() => setAsked("")); }}>
        {checking ? "Checking for updates…" : "Check for updates"}
      </button>
      {status.error && !checking && <span title={status.error}> · couldn't check</span>}
      {!status.error && status.latest && !checking && <span> · up to date</span>}
    </div>
  );
}
