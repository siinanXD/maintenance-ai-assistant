import {
  useEffect,
  useState,
  type ReactNode
} from "react";

import { loadMachineProfile } from "./machineApi";
import { MachineProfileView } from "./components/MachineProfileView";
import type { MachineProfile } from "./machineTypes";
import { machineErrorMessage } from "./machineUtils";

/**
 * Read the machine id from the React profile root.
 */
function readMachineId(): number | null {
  const reactRoot = document.getElementById("maintenance-machine-profile-root");
  const rawValue = reactRoot?.dataset.machineId || "";
  const machineId = Number(rawValue);
  return Number.isFinite(machineId) && machineId > 0 ? machineId : null;
}

/**
 * Render the React machine profile island.
 */
export function MachineProfileApp(): ReactNode {
  const [message, setMessage] = useState("Maschinenprofil wird geladen...");
  const [profile, setProfile] = useState<MachineProfile | null>(null);
  useEffect(() => {
    const machineId = readMachineId();
    if (!machineId) {
      setMessage("Maschinen-ID fehlt.");
      return;
    }

    loadMachineProfile(machineId)
      .then((loadedProfile) => {
        setProfile(loadedProfile);
        setMessage("");
      })
      .catch((error: unknown) => {
        setMessage(machineErrorMessage(error));
      });
  }, []);

  return <MachineProfileView message={message} profile={profile} />;
}
