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
        adminAi: resolve(configDirectory, "src/admin-ai/entry.tsx"),
        adminUsers: resolve(configDirectory, "src/admin-users/entry.tsx"),
        dashboard: resolve(configDirectory, "src/dashboard/entry.tsx"),
        documents: resolve(configDirectory, "src/documents/entry.tsx"),
        employees: resolve(configDirectory, "src/employees/entry.tsx"),
        errors: resolve(configDirectory, "src/errors/entry.tsx"),
        handover: resolve(configDirectory, "src/handover/entry.tsx"),
        inventory: resolve(configDirectory, "src/inventory/entry.tsx"),
        login: resolve(configDirectory, "src/login/entry.tsx"),
        machines: resolve(configDirectory, "src/machines/entry.tsx"),
        maintenance: resolve(configDirectory, "src/maintenance/entry.tsx"),
        shell: resolve(configDirectory, "src/layout/entry.tsx"),
        shiftplans: resolve(configDirectory, "src/shiftplans/entry.tsx"),
        tasks: resolve(configDirectory, "src/tasks/entry.tsx"),
        vacations: resolve(configDirectory, "src/vacations/entry.tsx")
      },
      output: {
        assetFileNames: "assets/[name]-[hash][extname]",
        chunkFileNames: "assets/[name]-[hash].js",
        entryFileNames: "assets/[name]-[hash].js"
      }
    }
  }
});
