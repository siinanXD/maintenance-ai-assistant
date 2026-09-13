import { useEffect, useRef, useState, type ReactNode } from "react";

import { fetchAuthorizedBlob } from "../../api/client";

type MachineQrLabelProps = {
  readonly machineId: number;
  readonly machineName: string;
};

/**
 * Button plus print dialog for the QR label that hangs on the machine.
 * Scanning the label opens the machine page; from there a technician can
 * report an incident in two taps.
 */
export function MachineQrLabel({ machineId, machineName }: MachineQrLabelProps): ReactNode {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [qrUrl, setQrUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => () => {
    if (qrUrl) URL.revokeObjectURL(qrUrl);
  }, [qrUrl]);

  /**
   * Load the QR code once and open the dialog.
   */
  async function openLabel(): Promise<void> {
    dialogRef.current?.showModal();
    if (qrUrl) return;
    try {
      setQrUrl(URL.createObjectURL(await fetchAuthorizedBlob(`/api/v1/machines/${machineId}/qr.svg`)));
      setError("");
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "QR-Code konnte nicht geladen werden.");
    }
  }

  return (
    <>
      <button className="btn btn-outline btn-sm" type="button" onClick={() => void openLabel()}>
        QR-Etikett
      </button>
      <dialog className="qr-label-dialog" ref={dialogRef} aria-labelledby="qr-label-title">
        <div className="qr-label-print">
          <p className="page-kicker">Maschine</p>
          <h2 id="qr-label-title">{machineName}</h2>
          {qrUrl ? <img alt={`QR-Code für ${machineName}`} src={qrUrl} /> : <div className="qr-label-placeholder">{error || "Wird erstellt…"}</div>}
          <p>Scannen öffnet die Maschinenakte. Dort Störung melden.</p>
          <small>Nr. {machineId}</small>
        </div>
        <div className="qr-label-actions">
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => dialogRef.current?.close()}>Schließen</button>
          <button className="btn btn-primary btn-sm" disabled={!qrUrl} type="button" onClick={() => window.print()}>Drucken</button>
        </div>
      </dialog>
    </>
  );
}
