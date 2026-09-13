import react from "@vitejs/plugin-react";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const configDirectory = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  base: "/static/react/",
  plugins: [react()],
  build: {
    outDir: "../app/static/react",
    emptyOutDir: true,
    manifest: true,
    sourcemap: false,
    rollupOptions: {
      input: {
        app: resolve(configDirectory, "src/main.tsx"),
        adminAi: resolve(configDirectory, "src/admin-ai/adminAiEntrypoint.tsx"),
        adminUsers: resolve(configDirectory, "src/admin-users/adminUsersEntrypoint.tsx"),
        dashboard: resolve(configDirectory, "src/dashboard/dashboardEntrypoint.tsx"),
        documents: resolve(configDirectory, "src/documents/documentsEntrypoint.tsx"),
        employees: resolve(configDirectory, "src/employees/employeesEntrypoint.tsx"),
        errors: resolve(configDirectory, "src/errors/errorsEntrypoint.tsx"),
        handover: resolve(configDirectory, "src/handover/handoverEntrypoint.tsx"),
        inventory: resolve(configDirectory, "src/inventory/inventoryEntrypoint.tsx"),
        login: resolve(configDirectory, "src/login/loginEntrypoint.tsx"),
        machines: resolve(configDirectory, "src/machines/machinesEntrypoint.tsx"),
        maintenance: resolve(configDirectory, "src/maintenance/maintenanceEntrypoint.tsx"),
        shellChrome: resolve(configDirectory, "src/layout/shellChromeEntrypoint.tsx"),
        shiftplans: resolve(configDirectory, "src/shiftplans/shiftplansEntrypoint.tsx"),
        tasks: resolve(configDirectory, "src/tasks/taskEntrypoint.tsx"),
        vacations: resolve(configDirectory, "src/vacations/vacationsEntrypoint.tsx")
      },
      output: {
        assetFileNames: "assets/[name]-[hash][extname]",
        chunkFileNames: "assets/[name]-[hash].js",
        entryFileNames: "assets/[name]-[hash].js"
      }
    }
  }
});
