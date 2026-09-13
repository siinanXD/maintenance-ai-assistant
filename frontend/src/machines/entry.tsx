import { mountPage } from "../app/mountPage";
import { MachineProfileApp } from "./MachineProfileApp";
import { MachinesOverviewApp } from "./MachinesOverviewApp";

// /machines and /machines/<id> share one bundle; each template provides one of the roots.
mountPage("maintenance-machines-root", <MachinesOverviewApp />);
mountPage("maintenance-machine-profile-root", <MachineProfileApp />);
