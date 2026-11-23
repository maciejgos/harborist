import { defineConfig } from "vite";

export default defineConfig({
  plugins: [{
    name: "trim-bundled-comment-whitespace",
    generateBundle(_, bundle) {
      for (const entry of Object.values(bundle)) {
        if (entry.type === "chunk") entry.code = entry.code.replace(/^[ \t]+$/gm, "");
      }
    },
  }],
  build: {
    outDir: "../src/harborist/web/assets",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "app.js",
        assetFileNames: ({ names }) => names.includes("harborist-mark.png")
          ? "harborist-mark.png" : "style[extname]",
      },
    },
  },
});
