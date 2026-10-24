import { build, preview } from "vite";

// One watch build per process: @originjs/vite-plugin-federation drops the
// exposed manifest from a second build in the same process. Serve once the
// first bundle is written; a busy preview port then fails the start.
const watcher = await build({ build: { watch: {} } });
await new Promise((resolve, reject) => {
  watcher.on("event", (event) => {
    if (event.code === "END") resolve();
    if (event.code === "ERROR") reject(event.error);
    if (event.result) event.result.close();
  });
});
const server = await preview();

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, async () => {
    await watcher.close();
    server.httpServer.close();
    process.exit(0);
  });
}
